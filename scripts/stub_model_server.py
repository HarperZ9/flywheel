"""A stub model server for the installed-app lane acceptance.

relay and local-model look for a model server at two fixed local addresses and
try ``127.0.0.1:8765`` first (``harness/local_agent.py``, relay
``local_agent.py``), with the serve.py protocol: ``GET /health`` answers
``{"ok": true}`` and ``POST /generate`` answers ``{"text", "model_ref",
"seed"}``. This stub answers that protocol and the OpenAI-shaped
``/v1/models`` and ``/v1/chat/completions`` with one fixed reply, so a lane run
ends on its first step with a final answer. It binds only a loopback address.

``GET /stats`` returns request counts per route. The acceptance reads it before
and after a model-lane call to show the call reached this stub and not another
model server on the host. The stub keeps counts only, never prompt text, and
logs nothing.

Usage: ``python scripts/stub_model_server.py [--port 8765] [--reply ok]``.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_REF = "wp11-stub"
REPLY_TEXT = "ok"
DEFAULT_PORT = 8765
_MAX_BODY = 1 << 20


class StubCounts:
    """Request counts per route, safe across handler threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts = {"health": 0, "generate": 0, "models": 0, "chat": 0}

    def bump(self, key: str) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)


def _chat_body(reply: str) -> dict:
    return {"id": "chatcmpl-wp11-stub", "object": "chat.completion", "created": 0,
            "model": MODEL_REF,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": reply}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 1, "total_tokens": 1}}


class _Handler(BaseHTTPRequestHandler):
    server_version = "wp11-stub/1"

    def log_message(self, *_args) -> None:  # the stub logs nothing
        return

    def _send(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict | None:
        try:
            size = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if size < 0 or size > _MAX_BODY:
            return None
        try:
            value = json.loads(self.rfile.read(size) or b"{}")
        except (ValueError, UnicodeDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        counts = self.server.counts
        path = self.path.split("?", 1)[0]
        if path == "/health":
            counts.bump("health")
            self._send(200, {"ok": True, "model_ref": MODEL_REF, "stub": True})
        elif path == "/v1/models":
            counts.bump("models")
            self._send(200, {"object": "list",
                             "data": [{"id": MODEL_REF, "object": "model"}]})
        elif path == "/stats":
            self._send(200, {"model_ref": MODEL_REF, "counts": counts.snapshot()})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 (http.server naming)
        path = self.path.split("?", 1)[0]
        if path not in ("/generate", "/v1/chat/completions"):
            self._send(404, {"error": "not found"})
            return
        body = self._read_json()
        if body is None:
            self._send(400, {"error": "request body must be a JSON object"})
            return
        reply = self.server.reply
        if path == "/generate":
            self.server.counts.bump("generate")
            seed = body.get("seed") if isinstance(body.get("seed"), int) else 0
            self._send(200, {"text": reply, "model_ref": MODEL_REF, "seed": seed})
        else:
            self.server.counts.bump("chat")
            self._send(200, _chat_body(reply))


def make_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                reply: str = REPLY_TEXT) -> ThreadingHTTPServer:
    """A stub bound to a loopback ``host``; ``port`` 0 picks a free port."""
    if not ipaddress.ip_address(host).is_loopback:
        raise ValueError("the stub model server binds a loopback address only")
    server = ThreadingHTTPServer((host, port), _Handler)
    server.daemon_threads = True
    server.counts = StubCounts()
    server.reply = reply
    return server


def start_in_thread(host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                    reply: str = REPLY_TEXT) -> ThreadingHTTPServer:
    """Start a stub on a daemon thread; the caller shuts it down."""
    server = make_server(host, port, reply)
    threading.Thread(target=server.serve_forever, name="wp11-stub",
                     daemon=True).start()
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--reply", default=REPLY_TEXT)
    args = parser.parse_args(argv)
    server = make_server(args.host, args.port, args.reply)
    print(json.dumps({"stub": MODEL_REF, "host": args.host,
                      "port": server.server_address[1]}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
