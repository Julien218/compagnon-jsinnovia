#!/usr/bin/env python3
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "avatar-factory.json").read_text(encoding="utf-8"))
WORKSPACE = ROOT / CONFIG["paths"]["workspace"]
JOBS_DIR = WORKSPACE / "jobs"
HOST = os.getenv("AVATAR_PREVIEW_HOST", "127.0.0.1")
PORT = int(os.getenv("AVATAR_PREVIEW_PORT", "8793"))
MAX_BYTES = 64 * 1024 * 1024
JOB_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,80}$")
ALLOWED_ORIGINS = {
    "https://cockpit.jsinnovia.com",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
}


class Handler(BaseHTTPRequestHandler):
    def _origin_allowed(self):
        origin = self.headers.get("Origin")
        return not origin or origin in ALLOWED_ORIGINS

    def _cors(self):
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if status != 204:
            self.wfile.write(body)

    def do_OPTIONS(self):
        if not self._origin_allowed():
            return self._json(403, {"error": "Origin not allowed"})
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if not self._origin_allowed():
            return self._json(403, {"error": "Origin not allowed"})
        path = urlparse(self.path).path
        if path == "/health":
            return self._json(200, {"ok": True, "service": "avatar-preview", "port": PORT})

        parts = [part for part in path.split("/") if part]
        if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "candidate.glb":
            job_id = parts[1]
            if not JOB_ID_RE.fullmatch(job_id):
                return self._json(400, {"error": "Job invalide"})
            candidate = (JOBS_DIR / job_id / "avatar-candidate.glb").resolve()
            jobs_root = JOBS_DIR.resolve()
            if jobs_root not in candidate.parents:
                return self._json(403, {"error": "Chemin interdit"})
            if not candidate.exists() or not candidate.is_file():
                return self._json(404, {"error": "Candidat 3D indisponible"})
            size = candidate.stat().st_size
            if size <= 0 or size > MAX_BYTES:
                return self._json(413, {"error": "Candidat 3D invalide ou trop volumineux"})
            data = candidate.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "model/gltf-binary")
            self._cors()
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        return self._json(404, {"error": "Route inconnue"})

    def log_message(self, fmt, *args):
        print(f"[avatar-preview] {self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    print(f"Avatar Preview API: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
