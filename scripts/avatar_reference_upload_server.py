#!/usr/bin/env python3
import base64
import binascii
import json
import os
import re
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "avatar-factory.json").read_text(encoding="utf-8"))
WORKSPACE = ROOT / CONFIG["paths"]["workspace"]
REFERENCES = WORKSPACE / "references"
REFERENCES.mkdir(parents=True, exist_ok=True)

HOST = os.getenv("AVATAR_REFERENCE_UPLOAD_HOST", "127.0.0.1")
PORT = int(os.getenv("AVATAR_REFERENCE_UPLOAD_PORT", "8792"))
MAX_BYTES = 12 * 1024 * 1024
SERVICE_VERSION = 3
ALLOWED_ORIGINS = {
    "https://cockpit.jsinnovia.com",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
}
ALLOWED_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
ALLOWED_VIEWS = {"front", "left", "back", "right"}
SUBJECT_KINDS = {"auto", "person", "animal", "bird", "object", "other"}
RIG_MODES = {"auto", "none", "humanoid", "quadruped", "avian", "generic"}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def safe_slug(value, fallback="avatar"):
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return (value or fallback)[:80]


def clean_text(value, fallback="", limit=160):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return (text or fallback)[:limit]


def normalize_subject_kind(value):
    kind = str(value or "auto").strip().lower()
    return kind if kind in SUBJECT_KINDS else "auto"


def default_rig_mode(subject_kind):
    return {
        "person": "humanoid",
        "animal": "quadruped",
        "bird": "avian",
        "object": "none",
        "other": "generic",
        "auto": "none",
    }.get(subject_kind, "none")


def normalize_rig_mode(value, subject_kind):
    mode = str(value or "auto").strip().lower()
    if mode not in RIG_MODES:
        mode = "auto"
    return default_rig_mode(subject_kind) if mode == "auto" else mode


def relative_to_root(path):
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved)


def manifest_path_for(character_id):
    return ROOT / "characters" / safe_slug(character_id) / "manifest.json"


def base_manifest(character_id, subject_name, subject_kind, rig_mode):
    animated = rig_mode != "none"
    return {
        "schema_version": 2,
        "id": character_id,
        "name": subject_name or character_id,
        "created_by": "JS-Innov.IA Avatar Factory",
        "created_at": utcnow(),
        "updated_at": utcnow(),
        "subject": {
            "kind": subject_kind,
            "rig_mode": rig_mode,
            "animation_enabled": animated,
        },
        "reference": {
            "status": "pending_upload",
            "canonical_path": "",
            "views": {},
        },
        "runtime": {
            "target_format": "GLB",
            "fallback_format": "GLB",
            "max_web_asset_mib": 15,
            "required_states": ["idle"] if animated else ["static"],
        },
        "production": {
            "turnaround_required": False,
            "human_approval_after_turnaround": True,
            "human_approval_before_publish": True,
            "default_compute": "local",
        },
    }


def load_manifest(path):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def upsert_character_manifest(payload, reference_path=None, view="front"):
    character_id = safe_slug(payload.get("character_id"), "avatar")
    subject_name = clean_text(payload.get("subject_name"), character_id)
    subject_kind = normalize_subject_kind(payload.get("subject_kind"))
    rig_mode = normalize_rig_mode(payload.get("rig_mode"), subject_kind)
    path = manifest_path_for(character_id)
    manifest = load_manifest(path) or base_manifest(character_id, subject_name, subject_kind, rig_mode)

    manifest["schema_version"] = max(2, int(manifest.get("schema_version") or 0))
    manifest["id"] = character_id
    manifest["name"] = subject_name
    manifest.setdefault("created_by", "JS-Innov.IA Avatar Factory")
    manifest.setdefault("created_at", utcnow())
    manifest["updated_at"] = utcnow()

    subject = manifest.setdefault("subject", {})
    subject["kind"] = subject_kind
    subject["rig_mode"] = rig_mode
    subject["animation_enabled"] = rig_mode != "none"

    reference = manifest.setdefault("reference", {})
    views = reference.setdefault("views", {})
    if reference_path:
        view = view if view in ALLOWED_VIEWS else "front"
        stored_path = relative_to_root(reference_path)
        views[view] = stored_path
        if view == "front" or not reference.get("canonical_path"):
            reference["canonical_path"] = stored_path
        reference["status"] = "uploaded"
    reference["available_views"] = sorted(views.keys())
    manifest.setdefault("production", {})["turnaround_required"] = all(
        candidate in views for candidate in ("front", "left", "back", "right")
    )

    runtime = manifest.setdefault("runtime", {})
    runtime.setdefault("target_format", "GLB")
    runtime.setdefault("fallback_format", "GLB")
    runtime.setdefault("max_web_asset_mib", 15)
    runtime["required_states"] = ["idle"] if rig_mode != "none" else ["static"]

    atomic_write_json(path, manifest)
    return {
        "manifest": manifest,
        "manifest_path": str(path.resolve()),
        "manifest_relative_path": relative_to_root(path),
    }


def validate_signature(data, mime):
    if mime == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if mime == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def save_reference(payload):
    mime = str(payload.get("mime_type") or "").lower()
    if mime not in ALLOWED_MIME:
        raise ValueError("Format accepté : PNG, JPG/JPEG ou WEBP")

    encoded = str(payload.get("data_base64") or "")
    if not encoded:
        raise ValueError("Image manquante")

    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Image encodée invalide")

    if not data:
        raise ValueError("Image vide")
    if len(data) > MAX_BYTES:
        raise ValueError("Image trop volumineuse : maximum 12 Mo")
    if not validate_signature(data, mime):
        raise ValueError("Le contenu du fichier ne correspond pas au format annoncé")

    character_id = safe_slug(payload.get("character_id"), "avatar")
    view = str(payload.get("view") or "front").strip().lower()
    if view not in ALLOWED_VIEWS:
        raise ValueError("Vue invalide : front, left, back ou right")
    original = safe_slug(Path(str(payload.get("file_name") or "reference")).stem, "reference")
    folder = REFERENCES / character_id
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{view}-{original}-{uuid.uuid4().hex[:12]}{ALLOWED_MIME[mime]}"
    target = folder / filename
    target.write_bytes(data)

    manifest_result = upsert_character_manifest(payload, target, view)
    manifest = manifest_result["manifest"]
    return {
        "ok": True,
        "reference_path": str(target.resolve()),
        "relative_path": relative_to_root(target),
        "file_name": filename,
        "mime_type": mime,
        "bytes": len(data),
        "character_id": character_id,
        "view": view,
        "subject_kind": manifest["subject"]["kind"],
        "rig_mode": manifest["subject"]["rig_mode"],
        "manifest_path": manifest_result["manifest_path"],
        "manifest_relative_path": manifest_result["manifest_relative_path"],
    }


def register_subject(payload):
    character_id = safe_slug(payload.get("character_id"), "")
    if not character_id:
        raise ValueError("character_id requis")
    result = upsert_character_manifest(payload)
    manifest = result["manifest"]
    return {
        "ok": True,
        "character_id": character_id,
        "subject_kind": manifest["subject"]["kind"],
        "rig_mode": manifest["subject"]["rig_mode"],
        "manifest_path": result["manifest_path"],
        "manifest_relative_path": result["manifest_relative_path"],
        "available_views": manifest.get("reference", {}).get("available_views", []),
    }


def get_subject(character_id):
    path = manifest_path_for(character_id)
    manifest = load_manifest(path)
    if not manifest:
        return None
    return {
        "ok": True,
        "manifest": manifest,
        "manifest_path": str(path.resolve()),
        "manifest_relative_path": relative_to_root(path),
    }


class Handler(BaseHTTPRequestHandler):
    def _cors_origin(self):
        origin = self.headers.get("Origin")
        return origin if origin in ALLOWED_ORIGINS else None

    def _origin_allowed(self):
        origin = self.headers.get("Origin")
        return not origin or origin in ALLOWED_ORIGINS

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
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if status != 204:
            self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        if length > 18 * 1024 * 1024:
            raise ValueError("Requête trop volumineuse")
        return json.loads(self.rfile.read(length))

    def do_OPTIONS(self):
        if not self._origin_allowed():
            return self._json(403, {"error": "Origin not allowed"})
        return self._json(204, {})

    def do_GET(self):
        if not self._origin_allowed():
            return self._json(403, {"error": "Origin not allowed"})
        path = urlparse(self.path).path
        if path == "/health":
            return self._json(200, {
                "ok": True,
                "service": "avatar-reference-upload",
                "version": SERVICE_VERSION,
                "port": PORT,
                "max_bytes": MAX_BYTES,
                "references_dir": str(REFERENCES.resolve()),
                "capabilities": {
                    "generic_subjects": True,
                    "auto_manifest": True,
                    "single_view": True,
                    "four_view": True,
                    "subject_kinds": sorted(SUBJECT_KINDS),
                    "rig_modes": sorted(RIG_MODES),
                },
            })
        if path.startswith("/subjects/"):
            character_id = unquote(path.split("/", 2)[2])
            subject = get_subject(character_id)
            return self._json(200 if subject else 404, subject or {"error": "Sujet introuvable"})
        return self._json(404, {"error": "Route inconnue"})

    def do_POST(self):
        if not self._origin_allowed():
            return self._json(403, {"error": "Origin not allowed"})
        path = urlparse(self.path).path
        try:
            if path == "/references/upload":
                return self._json(201, save_reference(self._body()))
            if path == "/subjects/register":
                return self._json(201, register_subject(self._body()))
            return self._json(404, {"error": "Route inconnue"})
        except ValueError as exc:
            return self._json(400, {"error": str(exc)})
        except Exception as exc:
            return self._json(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print(f"[avatar-reference-upload] {self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    print(f"Avatar Reference Upload API v{SERVICE_VERSION}: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
