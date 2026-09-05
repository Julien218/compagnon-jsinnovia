#!/usr/bin/env python3
"""Outbound-only Ollama worker for JS-Innov.IA AI Core.

Security model:
- Ollama remains on 127.0.0.1:11434; no inbound public port is opened.
- This process polls the Railway agent over HTTPS.
- Only the allow-listed Ollama chat models can run.
- The worker cannot execute shell commands, touch Cockpit data or call arbitrary URLs.
"""

import json
import os
import platform
import socket
import sys
import time
import urllib.error
import urllib.request

AGENT_URL = os.getenv("JSINNOVIA_AGENT_URL", "https://jsinnovia-agent-production.up.railway.app").rstrip("/")
BRIDGE_KEY = os.getenv("LOCAL_LLM_BRIDGE_KEY", "").strip()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
WORKER_ID = os.getenv("LOCAL_LLM_WORKER_ID", f"windows:{socket.gethostname()}")[:120]
POLL_SECONDS = max(1.0, float(os.getenv("LOCAL_LLM_POLL_SECONDS", "2")))
HEARTBEAT_SECONDS = max(10.0, float(os.getenv("LOCAL_LLM_HEARTBEAT_SECONDS", "20")))
ALLOWED_MODELS = {"qwen3.5:4b", "llama3.2:3b"}
APP_VERSION = "1.0.0"


def http_json(url, method="GET", payload=None, headers=None, timeout=30):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw or "{}")


def bridge_headers():
    return {
        "x-local-bridge-key": BRIDGE_KEY,
        "x-local-worker-id": WORKER_ID,
    }


def ollama_models():
    data = http_json(f"{OLLAMA_URL}/api/tags", timeout=5)
    found = []
    for item in data.get("models", []):
        name = str(item.get("name") or item.get("model") or "").strip()
        if name in ALLOWED_MODELS:
            found.append(name)
    return sorted(set(found))


def ollama_version():
    try:
        return str(http_json(f"{OLLAMA_URL}/api/version", timeout=5).get("version") or "")
    except Exception:
        return "unknown"


def worker_payload(models, status="online", last_error=None):
    return {
        "worker_id": WORKER_ID,
        "status": status,
        "models": models,
        "hostname": socket.gethostname(),
        "app_version": APP_VERSION,
        "last_error": last_error,
        "capabilities": {
            "provider": "ollama",
            "platform": platform.platform(),
            "python": platform.python_version(),
            "ollama_version": ollama_version(),
            "think_disabled": True,
            "outbound_only": True,
        },
    }


def heartbeat(models, status="online", last_error=None):
    return http_json(
        f"{AGENT_URL}/local-bridge-worker/heartbeat",
        method="POST",
        payload=worker_payload(models, status=status, last_error=last_error),
        headers=bridge_headers(),
        timeout=15,
    )


def claim(models):
    payload = worker_payload(models)
    payload["lease_seconds"] = 120
    return http_json(
        f"{AGENT_URL}/local-bridge-worker/claim",
        method="POST",
        payload=payload,
        headers=bridge_headers(),
        timeout=20,
    ).get("job")


def run_ollama(job):
    model = str(job.get("model") or "").strip()
    if model not in ALLOWED_MODELS:
        raise RuntimeError(f"Model not allowed: {model}")

    messages = []
    for item in list(job.get("messages") or [])[-20:]:
        role = str(item.get("role") or "user")
        if role not in {"system", "user", "assistant"}:
            role = "user"
        content = str(item.get("content") or "").strip()[:20000]
        if content:
            messages.append({"role": role, "content": content})
    if not messages:
        raise RuntimeError("No valid messages")

    options = job.get("options") if isinstance(job.get("options"), dict) else {}
    temperature = min(2.0, max(0.0, float(options.get("temperature", 0.2))))
    num_ctx = min(8192, max(512, int(options.get("num_ctx", 4096))))

    response = http_json(
        f"{OLLAMA_URL}/api/chat",
        method="POST",
        payload={
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        },
        timeout=180,
    )
    content = str((response.get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("Ollama returned an empty response")
    return {
        "response": content,
        "usage": {
            "prompt_eval_count": int(response.get("prompt_eval_count") or 0),
            "eval_count": int(response.get("eval_count") or 0),
        },
        "metadata": {
            "total_duration_ns": int(response.get("total_duration") or 0),
            "load_duration_ns": int(response.get("load_duration") or 0),
            "prompt_eval_duration_ns": int(response.get("prompt_eval_duration") or 0),
            "eval_duration_ns": int(response.get("eval_duration") or 0),
        },
    }


def submit_result(job_id, models, result=None, error=None):
    payload = worker_payload(models, status="online" if error is None else "degraded", last_error=error)
    payload.update({
        "ok": error is None,
        "response": (result or {}).get("response", ""),
        "usage": (result or {}).get("usage", {}),
        "metadata": (result or {}).get("metadata", {}),
        "error": error,
    })
    return http_json(
        f"{AGENT_URL}/local-bridge-worker/jobs/{job_id}/result",
        method="POST",
        payload=payload,
        headers=bridge_headers(),
        timeout=20,
    )


def main():
    if not BRIDGE_KEY:
        print("LOCAL_LLM_BRIDGE_KEY is required. Pair the Windows worker with Railway before starting.", file=sys.stderr)
        return 2
    if not AGENT_URL.startswith("https://") and "127.0.0.1" not in AGENT_URL and "localhost" not in AGENT_URL:
        print("JSINNOVIA_AGENT_URL must use HTTPS.", file=sys.stderr)
        return 2
    if not OLLAMA_URL.startswith("http://127.0.0.1") and not OLLAMA_URL.startswith("http://localhost"):
        print("OLLAMA_URL must stay on localhost.", file=sys.stderr)
        return 2

    print(f"JS-Innov.IA local LLM bridge started: {WORKER_ID}")
    print(f"Cloud: {AGENT_URL}")
    print(f"Ollama: {OLLAMA_URL} (localhost only)")
    last_heartbeat = 0.0
    backoff = POLL_SECONDS

    while True:
        try:
            models = ollama_models()
            if not models:
                raise RuntimeError("No allowed Ollama model found (qwen3.5:4b / llama3.2:3b)")

            now = time.time()
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                heartbeat(models)
                last_heartbeat = now

            job = claim(models)
            if not job:
                backoff = POLL_SECONDS
                time.sleep(POLL_SECONDS)
                continue

            print(f"Job {job['id']} -> {job['model']}")
            try:
                result = run_ollama(job)
                submit_result(job["id"], models, result=result)
                print(f"Job {job['id']} completed")
            except Exception as exc:
                message = str(exc)[:1500]
                try:
                    submit_result(job["id"], models, error=message)
                finally:
                    print(f"Job {job['id']} failed: {message}", file=sys.stderr)
            backoff = POLL_SECONDS
        except KeyboardInterrupt:
            print("Bridge stopped by user")
            return 0
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, ValueError) as exc:
            message = str(exc)[:1500]
            print(f"Bridge warning: {message}", file=sys.stderr)
            try:
                models = ollama_models()
                heartbeat(models, status="degraded", last_error=message)
            except Exception:
                pass
            time.sleep(backoff)
            backoff = min(30.0, max(POLL_SECONDS, backoff * 1.7))


if __name__ == "__main__":
    raise SystemExit(main())
