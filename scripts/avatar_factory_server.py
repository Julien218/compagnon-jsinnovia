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

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "avatar-factory.json").read_text(encoding="utf-8"))
WORKSPACE = ROOT / CONFIG["paths"]["workspace"]
WORKSPACE.mkdir(parents=True, exist_ok=True)
DB = WORKSPACE / "avatar_factory.sqlite3"
JOB_QUEUE = queue.Queue()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def db():
    conn = sqlite3.connect(DB)
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
            (job_id, stage, level, message, json.dumps(payload or {}), utcnow()),
        )


def update_job(job_id, **fields):
    fields["updated_at"] = utcnow()
    cols = ",".join(f"{k}=?" for k in fields)
    with db() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", [*fields.values(), job_id])


def record_cost(job, category, cost_eur, quantity=0, unit=None, provider="local", model=None, metadata=None):
    policy = job["billing_policy"]
    markup = float(CONFIG["finops"].get("default_markup_percent", 0)) / 100.0
    if policy == "technical_costs_only":
        billable = cost_eur
    elif policy == "standard_margin":
        billable = cost_eur * (1.0 + markup)
    elif policy == "fixed_plus_overage":
        billable = cost_eur
    else:
        billable = cost_eur
    with db() as conn:
        conn.execute(
            "INSERT INTO costs(job_id,category,provider,model,quantity,unit,cost_eur,billable_eur,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (job["id"], category, provider, model, quantity, unit, round(cost_eur, 6), round(billable, 6), json.dumps(metadata or {}), utcnow()),
        )


def timed_local_cost(job, stage, seconds, gpu=False):
    f = CONFIG["finops"]
    hours = seconds / 3600.0
    machine = hours * float(f["machine_amortization_hour_rate"])
    cpu = hours * float(f["cpu_hour_rate"])
    electric_kw = float(f["estimated_gpu_kw"] if gpu else f["estimated_cpu_kw"])
    electricity = hours * electric_kw * float(f["electricity_kwh_rate"])
    record_cost(job, "machine_amortization", machine, hours, "hour", metadata={"stage": stage})
    record_cost(job, "gpu_local" if gpu else "cpu_local", hours * float(f["gpu_hour_rate"] if gpu else f["cpu_hour_rate"]), hours, "hour", metadata={"stage": stage})
    record_cost(job, "electricity", electricity, hours * electric_kw, "kWh", metadata={"stage": stage})


def command_available(cmd):
    first = cmd[0]
    if os.path.isabs(first):
        return Path(first).exists()
    return shutil.which(first) is not None


def execute_stage(job, stage):
    if stage in CONFIG.get("approval_gates", []):
        update_job(job["id"], status="awaiting_approval", current_stage=stage)
        emit(job["id"], stage, "Validation humaine requise")
        return "pause"

    cmd = CONFIG.get("commands", {}).get(stage)
    if not cmd:
        emit(job["id"], stage, "Étape logique terminée (aucune commande externe requise)")
        return "ok"

    resolved = [str(ROOT / p) if i > 0 and isinstance(p, str) and p.startswith("scripts/") else p for i, p in enumerate(cmd)]
    if not command_available(resolved):
        raise RuntimeError(f"Commande indisponible: {resolved[0]}")

    started = time.perf_counter()
    emit(job["id"], stage, "Exécution démarrée", payload={"command": resolved})
    proc = subprocess.run(resolved, cwd=ROOT, capture_output=True, text=True, timeout=60 * 90)
    elapsed = time.perf_counter() - started
    timed_local_cost(job, stage, elapsed, gpu=(stage == "shape_3d"))
    if proc.returncode != 0:
        emit(job["id"], stage, "Échec de l'étape", "error", {"stderr": proc.stderr[-4000:]})
        raise RuntimeError(proc.stderr[-1000:] or f"Exit code {proc.returncode}")
    emit(job["id"], stage, "Étape terminée", payload={"seconds": round(elapsed, 2), "stdout": proc.stdout[-2000:]})
    return "ok"


def run_job(job_id):
    with db() as conn:
        job = rowdict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    if not job:
        return
    update_job(job_id, status="running")
    emit(job_id, None, "Production démarrée")
    try:
        pipeline = CONFIG["pipeline"]
        start_idx = 0
        if job.get("current_stage") in pipeline:
            start_idx = pipeline.index(job["current_stage"])
            if job["status"] == "queued_after_approval":
                start_idx += 1
        for stage in pipeline[start_idx:]:
            update_job(job_id, current_stage=stage, status="running")
            result = execute_stage(job, stage)
            if result == "pause":
                return
        update_job(job_id, status="completed", current_stage="completed")
        emit(job_id, "completed", "Avatar prêt à valider / publier")
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))
        emit(job_id, job.get("current_stage"), str(exc), "error")


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
    policy = payload.get("billing_policy", "standard_margin")
    if policy not in {"standard_margin", "fixed_plus_overage", "technical_costs_only", "custom"}:
        raise ValueError("billing_policy invalide")
    job_id = str(uuid.uuid4())
    now = utcnow()
    with db() as conn:
        conn.execute(
            "INSERT INTO jobs(id,client_id,entity_id,project_id,character_id,billing_policy,status,current_stage,created_at,updated_at,input_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, payload["client_id"], payload["entity_id"], payload["project_id"], payload["character_id"], policy, "queued", None, now, now, json.dumps(payload)),
        )
    emit(job_id, None, "Job créé")
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
    with db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    job = dict(row)
    if job["status"] != "awaiting_approval":
        raise ValueError("Ce job n'attend pas de validation")
    update_job(job_id, status="queued_after_approval")
    emit(job_id, job["current_stage"], "Validation humaine accordée")
    JOB_QUEUE.put(job_id)
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
    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._json(204, {})

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self._json(200, {"ok": True, "service": "avatar-factory", "version": 1, "workspace": str(WORKSPACE)})
        if path == "/jobs":
            return self._json(200, {"jobs": list_jobs()})
        if path == "/costs/summary":
            return self._json(200, summary())
        if path.startswith("/jobs/"):
            job = get_job(path.split("/")[2])
            return self._json(200 if job else 404, job or {"error": "Job introuvable"})
        self._json(404, {"error": "Route inconnue"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/jobs":
                return self._json(201, create_job(self._body()))
            if path.startswith("/jobs/") and path.endswith("/approve"):
                job_id = path.split("/")[2]
                job = approve(job_id)
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
