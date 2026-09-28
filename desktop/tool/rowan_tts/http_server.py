from __future__ import annotations

import json
import math
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .jobs import RowanTtsState, ServiceError


class RowanTtsHttpServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], state: RowanTtsState):
        super().__init__(server_address, RowanTtsHandler)
        self.state = state


class RowanTtsHandler(BaseHTTPRequestHandler):
    server: RowanTtsHttpServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        try:
            self._guard()
            parsed = urlparse(self.path)
            if parsed.path == "/v1/health":
                self._json(200, self.server.state.health())
                return
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["v1", "jobs"]:
                self._json(200, self.server.state.get(parts[2]).public_summary())
                return
            if len(parts) == 4 and parts[:2] == ["v1", "jobs"] and parts[3] == "audio":
                self._audio(parts[2])
                return
            raise ServiceError(404, "NOT_FOUND", "route was not found")
        except ServiceError as exc:
            self._json(exc.status, exc.body())

    def do_POST(self) -> None:
        try:
            self._guard()
            parsed = urlparse(self.path)
            if parsed.path == "/v1/speak":
                self._speak(parse_qs(parsed.query))
                return
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["v1", "jobs"] and parts[3] == "cancel":
                job = self.server.state.cancel(parts[2])
                self._json(200, job.public_summary())
                return
            if parsed.path == "/v1/stop":
                self.server.state.stop()
                self._json(200, {"schema": "rowan.local-tts-stop/v1", "ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            raise ServiceError(404, "NOT_FOUND", "route was not found")
        except ServiceError as exc:
            self._json(exc.status, exc.body())

    def _speak(self, query: dict[str, list[str]]) -> None:
        payload = self._read_json()
        wait = _bool_field(payload.pop("wait", False), "wait")
        if "wait" in query:
            query_wait = query.get("wait", ["false"])[0].lower()
            if query_wait not in {"true", "false"}:
                raise ServiceError(400, "BAD_WAIT", "wait query must be true or false")
            wait = query_wait == "true"
        timeout_s = _timeout_field(payload.pop("timeout_s", 120.0))
        timeout_s = min(max(timeout_s, 0.0), 300.0)
        job = self.server.state.submit(payload)
        if wait:
            self.server.state.wait(job, timeout_s)
        status = 200 if job.terminal else 202
        body = job.public_summary()
        body["ok"] = job.state == "completed"
        body["job_url"] = f"/v1/jobs/{job.job_id}"
        body["audio_url"] = f"/v1/jobs/{job.job_id}/audio" if job.output_path else None
        self._json(status, body)

    def _audio(self, job_id: str) -> None:
        job = self.server.state.get(job_id)
        if job.state != "completed" or job.output_path is None:
            raise ServiceError(409, "AUDIO_NOT_READY", "audio is not ready")
        data = job.output_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _guard(self) -> None:
        host = self.client_address[0]
        if host not in {"127.0.0.1", "::1"}:
            raise ServiceError(403, "NON_LOOPBACK_CLIENT", "client is not loopback")
        expected = f"Bearer {self.server.state.token}"
        auth = self.headers.get("Authorization", "")
        alt = self.headers.get("X-Rowan-TTS-Token", "")
        if auth != expected and alt != self.server.state.token:
            raise ServiceError(401, "UNAUTHORIZED", "missing or invalid token")

    def _read_json(self) -> dict[str, Any]:
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            raise ServiceError(411, "LENGTH_REQUIRED", "Content-Length is required")
        try:
            length = int(raw_len)
        except ValueError as exc:
            raise ServiceError(400, "BAD_LENGTH", "Content-Length is invalid") from exc
        if length > 65536:
            raise ServiceError(413, "BODY_TOO_LARGE", "body exceeds limit")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as exc:
            raise ServiceError(400, "BAD_JSON", "body must be JSON") from exc
        if not isinstance(value, dict):
            raise ServiceError(400, "BAD_JSON", "body must be a JSON object")
        return value

    def _json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_server(host: str, port: int, state: RowanTtsState) -> RowanTtsHttpServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Rowan local TTS binds only to loopback")
    return RowanTtsHttpServer((host, port), state)


def status_name(code: int) -> str:
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return "status"


def _bool_field(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ServiceError(400, f"BAD_{name.upper()}", f"{name} must be a boolean")
    return value


def _timeout_field(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ServiceError(400, "BAD_TIMEOUT", "timeout_s must be a number")
    timeout_s = float(value)
    if not math.isfinite(timeout_s):
        raise ServiceError(400, "BAD_TIMEOUT", "timeout_s must be finite")
    return timeout_s
