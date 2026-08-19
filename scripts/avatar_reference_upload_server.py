#!/usr/bin/env python3
import base64
import binascii
import json
import os
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "avatar-factory.json").read_text(encoding="utf-8"))
WORKSPACE = ROOT / CONFIG["paths"]["workspace"]
REFERENCES = WORKSPACE / "references"
REFERENCES.mkdir(parents=True, exist_ok=True)

HOST = os.getenv("AVATAR_REFERENCE_UPLOAD_HOST", "127.0.0.1")
PORT = int(os.getenv("AVATAR_REFERENCE_UPLOAD_PORT", "8792"))
MAX_BYTES = 12 * 1024 * 1024
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


def safe_slug(value, fallback="avatar"):
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return (value or fallback)[:80]


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
    original = safe_slug(Path(str(payload.get("file_name") or "reference")).stem, "reference")
    folder = REFERENCES / character_id
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{original}-{uuid.uuid4().hex[:12]}{ALLOWED_MIME[mime]}"
    target = folder / filename
    target.write_bytes(data)

    return {
        "ok": True,
        "reference_path": str(target.resolve()),
        "relative_path": str(target.relative_to(ROOT)).replace("\\", "/"),
        "file_name": filename,
        "mime_type": mime,
        "bytes": len(data),
        "character_id": character_id,
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
                "port": PORT,
                "max_bytes": MAX_BYTES,
                "references_dir": str(REFERENCES.resolve()),
            })
        return self._json(404, {"error": "Route inconnue"})

    def do_POST(self):
        if not self._origin_allowed():
            return self._json(403, {"error": "Origin not allowed"})
        path = urlparse(self.path).path
        try:
            if path == "/references/upload":
                return self._json(201, save_reference(self._body()))
            return self._json(404, {"error": "Route inconnue"})
        except ValueError as exc:
            return self._json(400, {"error": str(exc)})
        except Exception as exc:
            return self._json(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print(f"[avatar-reference-upload] {self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    print(f"Avatar Reference Upload API: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
