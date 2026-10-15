"""model.py -- a scripted OpenAI-compatible model that records request bodies.

Serves POST /v1/chat/completions on a loopback port and answers with the next
reply from a fixed script; once the script runs out it repeats the last reply.
Every request body is kept in order, as parsed JSON, so a behavior check can
compare what two builds sent. GET /v1/models lists one model. Standard library
only; it binds a loopback address and never forwards anything.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_ID = "behavior-check-stub"
_MAX_BODY = 8 << 20


class _Handler(BaseHTTPRequestHandler):
    server_version = "behavior-check-stub/1"

    def log_message(self, *_args) -> None:  # the stub logs nothing
        return

    def _send(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        if self.path.split("?", 1)[0].rstrip("/").endswith("/models"):
            self._send(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 (http.server naming)
        if not self.path.split("?", 1)[0].endswith("/chat/completions"):
            self._send(404, {"error": "not found"})
            return
        try:
            size = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(max(size, 0), _MAX_BODY)) or b"{}")
        except ValueError:
            body = {"unparsed": True}
        self._send(200, self.server.script.answer(body))


class Script:
    """The replies in order, and the request bodies received, in order."""

    def __init__(self, replies: list) -> None:
        self.replies = [str(r) for r in replies] or ["Done."]
        self.requests: list = []
        self._lock = threading.Lock()

    def answer(self, body) -> dict:
        with self._lock:
            index = len(self.requests)
            self.requests.append(body)
            text = self.replies[min(index, len(self.replies) - 1)]
        return {"id": f"chatcmpl-stub-{index}", "object": "chat.completion", "created": 0,
                "model": MODEL_ID,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}


class ScriptedModel:
    """A running scripted model; use as a context manager."""

    def __init__(self, replies: list, host: str = "127.0.0.1") -> None:
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise ValueError("the scripted model binds a loopback address only")
        self.script = Script(replies)
        self._server = ThreadingHTTPServer((host, 0), _Handler)
        self._server.daemon_threads = True
        self._server.script = self.script
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        name="behavior-check-stub", daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    @property
    def requests(self) -> list:
        return list(self.script.requests)

    def __enter__(self) -> "ScriptedModel":
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._server.shutdown()
        self._server.server_close()
