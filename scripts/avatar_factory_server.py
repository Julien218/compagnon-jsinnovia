#!/usr/bin/env python3
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from avatar_runtime_qa import evaluate_runtime_qa

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "avatar-factory.json").read_text(encoding="utf-8"))
WORKSPACE = ROOT / CONFIG["paths"]["workspace"]
WORKSPACE.mkdir(parents=True, exist_ok=True)
DB = WORKSPACE / "avatar_factory.sqlite3"
JOB_QUEUE = queue.Queue()
ALLOWED_ORIGINS = {
    "https://cockpit.jsinnovia.com",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def db():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          client_id TEXT NOT NULL,
          entity_id TEXT NOT NULL,
          project_id TEXT NOT NULL,
          character_id TEXT NOT NULL,
          billing_policy TEXT NOT NULL,
          status TEXT NOT NULL,
          current_stage TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          input_json TEXT NOT NULL,
          output_json TEXT NOT NULL DEFAULT '{}',
          error TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id TEXT NOT NULL,
          stage TEXT,
          level TEXT NOT NULL,
          message TEXT NOT NULL,
          payload_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS costs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id TEXT NOT NULL,
          category TEXT NOT NULL,
          provider TEXT,
          model TEXT,
          quantity REAL NOT NULL DEFAULT 0,
          unit TEXT,
          cost_eur REAL NOT NULL DEFAULT 0,
          billable_eur REAL NOT NULL DEFAULT 0,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL
        );
        """)


def rowdict(row):
    return dict(row) if row else None


def emit(job_id, stage, message, level="info", payload=None):
    with db() as conn:
        conn.execute(
            "INSERT INTO events(job_id,stage,level,message,payload_json,created_at) VALUES(?,?,?,?,?,?)",
            (job_id, stage, level, message, json.dumps(payload or {}, ensure_ascii=False), utcnow()),
        )


def update_job(job_id, **fields):
    fields["updated_at"] = utcnow()
    cols = ",".join(f"{k}=?" for k in fields)
    with db() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", [*fields.values(), job_id])


def read_job(job_id):
    with db() as conn:
        return rowdict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def job_input(job):
    return json.loads(job.get("input_json") or "{}")


def set_output(job_id, **changes):
    job = read_job(job_id)
    current = json.loads(job.get("output_json") or "{}") if job else {}
    current.update(changes)
    update_job(job_id, output_json=json.dumps(current, ensure_ascii=False))


def record_cost(job, category, cost_eur, quantity=0, unit=None, provider="local", model=None, metadata=None):
    policy = job["billing_policy"]
    markup = float(CONFIG["finops"].get("default_markup_percent", 0)) / 100.0
    if policy == "standard_margin":
        billable = cost_eur * (1.0 + markup)
    else:
        billable = cost_eur
    with db() as conn:
        conn.execute(
            "INSERT INTO costs(job_id,category,provider,model,quantity,unit,cost_eur,billable_eur,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (job["id"], category, provider, model, quantity, unit, round(cost_eur, 8), round(billable, 8), json.dumps(metadata or {}), utcnow()),
        )


def timed_local_cost(job, stage, seconds, gpu=False):
    f = CONFIG["finops"]
    hours = seconds / 3600.0
    electric_kw = float(f["estimated_gpu_kw"] if gpu else f["estimated_cpu_kw"])
    record_cost(job, "machine_amortization", hours * float(f["machine_amortization_hour_rate"]), hours, "hour", metadata={"stage": stage})
    record_cost(job, "gpu_local" if gpu else "cpu_local", hours * float(f["gpu_hour_rate"] if gpu else f["cpu_hour_rate"]), hours, "hour", metadata={"stage": stage})
    record_cost(job, "electricity", hours * electric_kw * float(f["electricity_kwh_rate"]), hours * electric_kw, "kWh", metadata={"stage": stage})


def character_manifest(character_id):
    path = ROOT / "characters" / character_id / "manifest.json"
    if not path.exists():
        raise RuntimeError(f"Character manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def reference_path(job):
    payload = job_input(job)
    if payload.get("reference_path"):
        path = Path(os.path.expandvars(os.path.expanduser(str(payload["reference_path"]))))
        if not path.is_absolute():
            path = ROOT / path
        return path.resolve()
    manifest = character_manifest(job["character_id"])
    return (ROOT / manifest["reference"]["canonical_path"]).resolve()


def artifact_paths(job):
    folder = WORKSPACE / "jobs" / job["id"]
    folder.mkdir(parents=True, exist_ok=True)
    return {
        "folder": folder,
        "raw": folder / "shape-raw.glb",
        "candidate": folder / "avatar-candidate.glb",
        "qa": folder / "avatar-candidate.qa.json",
        "runtime_qa": folder / "runtime-qa.json",
    }


def executable(value):
    if os.path.isabs(value):
        return value if Path(value).exists() else None
    return shutil.which(value)


def run_command(job, stage, command, gpu=False, timeout=5400):
    exe = executable(command[0])
    if not exe:
        raise RuntimeError(f"Executable unavailable: {command[0]}")
    command[0] = exe
    started = time.perf_counter()
    emit(job["id"], stage, "Exécution démarrée", payload={"command": command})
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    elapsed = time.perf_counter() - started
    timed_local_cost(job, stage, elapsed, gpu=gpu)
    if proc.returncode != 0:
        emit(job["id"], stage, "Échec de l'étape", "error", {"stderr": proc.stderr[-5000:], "stdout": proc.stdout[-2000:]})
        raise RuntimeError(proc.stderr[-1500:] or proc.stdout[-1500:] or f"Exit code {proc.returncode}")
    emit(job["id"], stage, "Étape terminée", payload={"seconds": round(elapsed, 2), "stdout": proc.stdout[-2500:]})
    return proc


def execute_stage(job, stage):
    paths = artifact_paths(job)
    payload = job_input(job)

    if stage == "reference_qa":
        ref = reference_path(job)
        references = [("front", ref)]
        for view in ("left", "back", "right"):
            key = f"{view}_reference_path"
            if payload.get(key):
                references.append((view, Path(os.path.expandvars(os.path.expanduser(str(payload[key]))))))
        validated = {}
        for view, path in references:
            if not path.exists() or not path.is_file():
                raise RuntimeError(f"{view} reference image missing: {path}")
            if path.stat().st_size < 10_000:
                raise RuntimeError(f"{view} reference image appears invalid or too small")
            suffix = path.suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                raise RuntimeError(f"Unsupported {view} reference format: {suffix}")
            validated[view] = {"path": str(path), "bytes": path.stat().st_size}
        output = {"reference_path": str(ref)}
        for view in ("left", "back", "right"):
            if view in validated:
                output[f"{view}_reference_path"] = validated[view]["path"]
        set_output(job["id"], **output)
        emit(job["id"], stage, "Références validées", payload=validated)
        return "ok"

    if stage == "shape_3d":
        ref = reference_path(job)
        preset = str(payload.get("preset") or CONFIG["routing"].get("default_preset", "diagnostic"))
        if preset not in {"diagnostic", "production"}:
            preset = "diagnostic"
        command = [
            "powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "run_avatar_comfyui.ps1"),
            "-CharacterId", job["character_id"], "-ReferencePath", str(ref), "-OutputPath", str(paths["raw"]), "-Preset", preset,
        ]
        for view, parameter in (("left", "-LeftReferencePath"), ("back", "-BackReferencePath"), ("right", "-RightReferencePath")):
            key = f"{view}_reference_path"
            if payload.get(key):
                command.extend([parameter, str(Path(os.path.expandvars(os.path.expanduser(str(payload[key])))))])
        seed = int(payload.get("seed") or 2182026)
        if seed < 1 or seed > 2147483646:
            raise RuntimeError("seed must be between 1 and 2147483646")
        command.extend(["-Seed", str(seed)])
        comfyui_root = os.getenv("COMFYUI_ROOT") or CONFIG["paths"].get("comfyui")
        if comfyui_root:
            command.extend(["-ComfyUIRoot", comfyui_root])
        run_command(job, stage, command, gpu=True)
        if not paths["raw"].exists():
            raise RuntimeError("ComfyUI completed but raw GLB was not materialized")
        multiview = all(payload.get(f"{view}_reference_path") for view in ("left", "back", "right"))
        set_output(job["id"], raw_glb=str(paths["raw"]), preset=preset, seed=seed, multiview=multiview, reference_views=4 if multiview else 1)
        return "ok"

    if stage == "blender_finalize":
        blender = os.getenv("BLENDER_EXE") or CONFIG["paths"].get("blender", "blender")
        command = [blender, "--background", "--python", str(ROOT / "scripts" / "blender_finalize_avatar.py"), "--", str(paths["raw"]), str(paths["candidate"])]
        run_command(job, stage, command, gpu=False)
        if not paths["candidate"].exists():
            raise RuntimeError("Blender did not produce the candidate GLB")
        set_output(job["id"], candidate_glb=str(paths["candidate"]), blender_qa=str(paths["qa"]))
        return "ok"

    if stage == "runtime_qa":
        candidate = paths["candidate"]
        qa_path = paths["qa"]
        if not candidate.exists() or not qa_path.exists():
            raise RuntimeError("Candidate or Blender QA report missing")
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        size_mib = candidate.stat().st_size / (1024 * 1024)
        max_mib = float(CONFIG["runtime"].get("max_validation_asset_mib", 25))
        max_components = int(CONFIG["runtime"].get("max_connected_components", 12))
        min_largest_ratio = float(CONFIG["runtime"].get("min_largest_component_ratio", 0.80))
        errors = evaluate_runtime_qa(size_mib, max_mib, qa, max_components, min_largest_ratio)
        report = {"ok": not errors, "size_mib": round(size_mib, 3), "max_mib": max_mib, "errors": errors, "blender": qa}
        paths["runtime_qa"].write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        set_output(job["id"], runtime_qa=str(paths["runtime_qa"]), validation_ready=not errors)
        if errors:
            raise RuntimeError("Runtime QA failed: " + ", ".join(errors))
        emit(job["id"], stage, "Runtime QA validé", payload=report)
        return "ok"

    if stage in CONFIG.get("approval_gates", []):
        update_job(job["id"], status="awaiting_approval", current_stage=stage)
        emit(job["id"], stage, "Candidat 3D prêt : validation visuelle humaine requise avant publication", payload={"candidate_glb": str(paths["candidate"])})
        return "pause"

    emit(job["id"], stage, "Étape logique terminée")
    return "ok"


def run_job(job_id):
    job = read_job(job_id)
    if not job:
        return
    previous_status = job["status"]
    update_job(job_id, status="running", error=None)
    emit(job_id, None, "Production démarrée")
    try:
        pipeline = CONFIG["pipeline"]
        start_idx = 0
        if job.get("current_stage") in pipeline:
            start_idx = pipeline.index(job["current_stage"])
            if previous_status == "queued_after_approval":
                start_idx += 1
        for stage in pipeline[start_idx:]:
            job = read_job(job_id)
            update_job(job_id, current_stage=stage, status="running")
            result = execute_stage(job, stage)
            if result == "pause":
                return
        update_job(job_id, status="completed", current_stage="completed")
        emit(job_id, "completed", "Candidat 3D approuvé et job terminé")
    except Exception as exc:
        current = read_job(job_id)
        update_job(job_id, status="failed", error=str(exc))
        emit(job_id, current.get("current_stage") if current else None, str(exc), "error")


def worker():
    while True:
        job_id = JOB_QUEUE.get()
        try:
            run_job(job_id)
        finally:
            JOB_QUEUE.task_done()


def create_job(payload):
    required = ["client_id", "entity_id", "project_id", "character_id"]
    missing = [k for k in required if not str(payload.get(k, "")).strip()]
    if missing:
        raise ValueError("Champs requis: " + ", ".join(missing))
    auxiliary_views = ["left_reference_path", "back_reference_path", "right_reference_path"]
    supplied_views = [key for key in auxiliary_views if str(payload.get(key, "")).strip()]
    if supplied_views and len(supplied_views) != len(auxiliary_views):
        missing_views = [key.replace("_reference_path", "") for key in auxiliary_views if key not in supplied_views]
        raise ValueError("Mode multivue incomplet. Vues manquantes: " + ", ".join(missing_views))
    character_manifest(str(payload["character_id"]))
    requested_policy = payload.get("billing_policy", "standard_margin")
    if requested_policy not in {"standard_margin", "fixed_plus_overage", "technical_costs_only", "custom"}:
        raise ValueError("billing_policy invalide")
    policy = "technical_costs_only" if str(payload["client_id"]).strip().lower() == "olivier" else requested_policy
    job_id = str(uuid.uuid4())
    now = utcnow()
    with db() as conn:
        conn.execute(
            "INSERT INTO jobs(id,client_id,entity_id,project_id,character_id,billing_policy,status,current_stage,created_at,updated_at,input_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, payload["client_id"], payload["entity_id"], payload["project_id"], payload["character_id"], policy, "queued", None, now, now, json.dumps(payload)),
        )
    emit(job_id, None, "Job créé", payload={"billing_policy": policy})
    JOB_QUEUE.put(job_id)
    return get_job(job_id)


def get_job(job_id):
    with db() as conn:
        job = rowdict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
        if not job:
            return None
        events = [dict(r) for r in conn.execute("SELECT * FROM events WHERE job_id=? ORDER BY id DESC LIMIT 100", (job_id,))]
        costs = [dict(r) for r in conn.execute("SELECT * FROM costs WHERE job_id=? ORDER BY id", (job_id,))]
    job["input"] = json.loads(job.pop("input_json"))
    job["output"] = json.loads(job.pop("output_json"))
    for event in events:
        event["payload"] = json.loads(event.pop("payload_json") or "{}")
    for cost in costs:
        cost["metadata"] = json.loads(cost.pop("metadata_json") or "{}")
    job["events"] = events
    job["costs"] = costs
    job["cost_total_eur"] = round(sum(float(c["cost_eur"]) for c in costs), 4)
    job["billable_total_eur"] = round(sum(float(c["billable_eur"]) for c in costs), 4)
    return job


def list_jobs():
    with db() as conn:
        rows = conn.execute("SELECT id,client_id,entity_id,project_id,character_id,billing_policy,status,current_stage,created_at,updated_at,error FROM jobs ORDER BY created_at DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


def approve(job_id):
    job = read_job(job_id)
    if not job:
        return None
    if job["status"] != "awaiting_approval":
        raise ValueError("Ce job n'attend pas de validation")
    update_job(job_id, status="queued_after_approval")
    emit(job_id, job["current_stage"], "Validation humaine accordée")
    JOB_QUEUE.put(job_id)
    return get_job(job_id)


def reject(job_id, reason="Validation visuelle refusée"):
    job = read_job(job_id)
    if not job:
        return None
    if job["status"] != "awaiting_approval":
        raise ValueError("Ce job n'attend pas de validation")
    update_job(job_id, status="rejected", error=reason)
    emit(job_id, job["current_stage"], reason, "warning")
    return get_job(job_id)


def summary():
    with db() as conn:
        totals = conn.execute("SELECT COALESCE(SUM(cost_eur),0), COALESCE(SUM(billable_eur),0) FROM costs").fetchone()
        by_entity = [dict(r) for r in conn.execute("""
          SELECT j.entity_id, j.client_id, COUNT(DISTINCT j.id) jobs,
                 ROUND(COALESCE(SUM(c.cost_eur),0),4) cost_eur,
                 ROUND(COALESCE(SUM(c.billable_eur),0),4) billable_eur
          FROM jobs j LEFT JOIN costs c ON c.job_id=j.id
          GROUP BY j.entity_id,j.client_id ORDER BY cost_eur DESC
        """)]
    return {"cost_eur": round(totals[0], 4), "billable_eur": round(totals[1], 4), "by_entity": by_entity}


class Handler(BaseHTTPRequestHandler):
    def _cors_origin(self):
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            return origin
        return None

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if status != 204:
            self.wfile.write(body)

    def _origin_allowed(self):
        origin = self.headers.get("Origin")
        return not origin or origin in ALLOWED_ORIGINS

    def do_OPTIONS(self):
        if not self._origin_allowed():
            return self._json(403, {"error": "Origin not allowed"})
        self._json(204, {})

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if not self._origin_allowed():
            return self._json(403, {"error": "Origin not allowed"})
        path = urlparse(self.path).path
        if path == "/health":
            return self._json(200, {"ok": True, "service": "avatar-factory", "version": CONFIG["version"], "workspace": str(WORKSPACE)})
        if path == "/jobs":
            return self._json(200, {"jobs": list_jobs()})
        if path == "/costs/summary":
            return self._json(200, summary())
        if path.startswith("/jobs/"):
            job = get_job(path.split("/")[2])
            return self._json(200 if job else 404, job or {"error": "Job introuvable"})
        self._json(404, {"error": "Route inconnue"})

    def do_POST(self):
        if not self._origin_allowed():
            return self._json(403, {"error": "Origin not allowed"})
        path = urlparse(self.path).path
        try:
            if path == "/jobs":
                return self._json(201, create_job(self._body()))
            if path.startswith("/jobs/") and path.endswith("/approve"):
                job = approve(path.split("/")[2])
                return self._json(200 if job else 404, job or {"error": "Job introuvable"})
            if path.startswith("/jobs/") and path.endswith("/reject"):
                payload = self._body()
                job = reject(path.split("/")[2], str(payload.get("reason") or "Validation visuelle refusée"))
                return self._json(200 if job else 404, job or {"error": "Job introuvable"})
            self._json(404, {"error": "Route inconnue"})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print(f"[avatar-factory] {self.address_string()} - {fmt % args}")


def main():
    init_db()
    threading.Thread(target=worker, daemon=True).start()
    host = os.getenv("AVATAR_FACTORY_HOST", CONFIG["server"]["host"])
    port = int(os.getenv("AVATAR_FACTORY_PORT", CONFIG["server"]["port"]))
    print(f"Avatar Factory API: http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
