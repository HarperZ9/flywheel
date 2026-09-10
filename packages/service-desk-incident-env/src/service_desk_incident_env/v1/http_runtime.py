"""Loopback HTTP runtime for ServiceDesk v1."""
from __future__ import annotations

import json
import secrets
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from harness.enterprise_envs.digest import digest_text

from .descriptor import ENVIRONMENT_ID
from .store import ServiceDeskStore


class ServiceDeskRuntime:
    def __init__(self, root: Path, run_id: str, instance_id: str):
        self.root = Path(root)
        self.run_id = run_id
        self.instance_id = instance_id
        self.store = ServiceDeskStore(self.root, run_id, instance_id)
        self.agent_token = f"agent_{secrets.token_urlsafe(24)}"
        self.control_token = f"control_{secrets.token_urlsafe(24)}"
        self.agent_token_ref = f"agent-token-digest:{digest_text(self.agent_token)}"
        self.control_token_ref = f"control-token-digest:{digest_text(self.control_token)}"
        self._agent_server: ThreadingHTTPServer | None = None
        self._control_server: ThreadingHTTPServer | None = None
        self._threads: list[threading.Thread] = []
        self.agent_base_url = ""
        self.control_base_url = ""
        self.tokens_invalidated = False

    def start(self) -> None:
        runtime = self

        class AgentHandler(_JsonHandler):
            def do_GET(self) -> None:  # noqa: N802
                runtime._handle_agent(self, "GET")

            def do_PATCH(self) -> None:  # noqa: N802
                runtime._handle_agent(self, "PATCH")

            def do_POST(self) -> None:  # noqa: N802
                runtime._handle_agent(self, "POST")

        class ControlHandler(_JsonHandler):
            def do_GET(self) -> None:  # noqa: N802
                runtime._handle_control(self, "GET")

            def do_POST(self) -> None:  # noqa: N802
                runtime._handle_control(self, "POST")

        self._agent_server = ThreadingHTTPServer(("127.0.0.1", 0), AgentHandler)
        self._control_server = ThreadingHTTPServer(("127.0.0.1", 0), ControlHandler)
        self.agent_base_url = f"http://127.0.0.1:{self._agent_server.server_port}"
        self.control_base_url = f"http://127.0.0.1:{self._control_server.server_port}"
        for server in (self._agent_server, self._control_server):
            thread = threading.Thread(
                target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        for server in (self._agent_server, self._control_server):
            if server is not None:
                server.shutdown()
                server.server_close()
        for thread in self._threads:
            thread.join(timeout=5)
        self._threads.clear()
        self._agent_server = None
        self._control_server = None
        self.store.close()

    def invalidate_tokens(self) -> None:
        self.agent_token = ""
        self.control_token = ""
        self.tokens_invalidated = True

    def runtime_agent_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.agent_token}", "Content-Type": "application/json"}

    def runtime_control_headers(self) -> dict[str, str]:
        return {"X-Flywheel-Control-Token": self.control_token, "Content-Type": "application/json"}

    def persisted_agent_view(self) -> dict[str, Any]:
        return {
            "schema": "flywheel.enterprise-environment-agent-view/v1",
            "environment_id": ENVIRONMENT_ID,
            "run_id": self.run_id,
            "instance_id": self.instance_id,
            "agent_base_url": self.agent_base_url,
            "token_ref": self.agent_token_ref,
            "token_value_persisted": False,
            "tokens_invalidated_before_artifacts": self.tokens_invalidated,
            "available_routes": [
                "GET /api/now/table/incident",
                "PATCH /api/now/table/incident/{sys_id}",
                "POST /api/now/attachment/file",
            ],
            "hidden_routes_excluded": ["GET /control/state", "POST /control/reset", "GET /control/action-log"],
        }

    def persisted_control_view(self) -> dict[str, Any]:
        return {
            "schema": "flywheel.enterprise-environment-control-view/v1",
            "environment_id": ENVIRONMENT_ID,
            "run_id": self.run_id,
            "instance_id": self.instance_id,
            "control_base_url": self.control_base_url,
            "token_ref": self.control_token_ref,
            "token_value_persisted": False,
            "agent_control_separate_ports": self._port(self.agent_base_url) != self._port(self.control_base_url),
            "control_routes": ["GET /control/state", "GET /control/action-log", "POST /control/reset"],
        }

    def _handle_agent(self, handler: "_JsonHandler", method: str) -> None:
        parsed = urlparse(handler.path)
        path = parsed.path
        token_ref = self._agent_request_token_ref(handler)
        if path.startswith("/control/"):
            response = self.store.denied(method, _template_for(path), token_ref, 404, "hidden_control_route_not_on_agent_port")
            handler.write_json(response["status"], response["body"])
            return
        if self.tokens_invalidated or handler.headers.get("Authorization") != f"Bearer {self.agent_token}":
            response = self.store.denied(method, _template_for(path), token_ref, 401, "agent_auth_failed")
            handler.write_json(response["status"], response["body"])
            return
        if method == "GET" and path == "/api/now/table/incident":
            response = self.store.list_incidents(token_ref)
            handler.write_json(response["status"], response["body"])
            return
        if method == "PATCH" and path.startswith("/api/now/table/incident/"):
            sys_id = path.rsplit("/", 1)[-1]
            parsed_body = handler.read_json_result()
            if parsed_body.error:
                response = self.store.denied(method, _template_for(path), token_ref, 400, parsed_body.error)
                handler.write_json(response["status"], response["body"])
                return
            response = self.store.patch_incident(sys_id, parsed_body.body, token_ref, handler.headers.get("Idempotency-Key"))
            handler.write_json(response["status"], response["body"])
            return
        if method == "POST" and path == "/api/now/attachment/file":
            parsed_body = handler.read_json_result()
            if parsed_body.error:
                response = self.store.denied(method, _template_for(path), token_ref, 400, parsed_body.error)
                handler.write_json(response["status"], response["body"])
                return
            response = self.store.add_attachment(parsed_body.body, token_ref, handler.headers.get("Idempotency-Key"))
            handler.write_json(response["status"], response["body"])
            return
        response = self.store.denied(method, _template_for(path), token_ref, 404, "route_not_found")
        handler.write_json(response["status"], response["body"])

    def _handle_control(self, handler: "_JsonHandler", method: str) -> None:
        parsed = urlparse(handler.path)
        path = parsed.path
        if self.tokens_invalidated or handler.headers.get("X-Flywheel-Control-Token") != self.control_token:
            handler.write_json(403, {"error": "control_auth_failed"})
            return
        if method == "GET" and path == "/control/state":
            handler.write_json(200, self.store.domain_state())
            return
        if method == "GET" and path == "/control/action-log":
            handler.write_json(200, self.store.action_log())
            return
        if method == "POST" and path == "/control/reset":
            handler.write_json(200, self.store.reset(clear_action_log=False))
            return
        handler.write_json(404, {"error": "control_route_not_found"})

    def _agent_request_token_ref(self, handler: "_JsonHandler") -> str:
        header = handler.headers.get("Authorization", "")
        if header == f"Bearer {self.agent_token}" and self.agent_token:
            return self.agent_token_ref
        if header.startswith("Bearer "):
            return "agent-token-digest:invalid"
        return "agent-token-digest:missing"

    @staticmethod
    def _port(url: str) -> str:
        return urlparse(url).port or ""


class _JsonHandler(BaseHTTPRequestHandler):
    server_version = "FlywheelServiceDesk/1"

    def log_message(self, _format: str, *args: object) -> None:
        return

    def read_json_result(self) -> "_JsonParseResult":
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            return _JsonParseResult({}, "json_body_invalid")
        if length <= 0:
            return _JsonParseResult({}, None)
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _JsonParseResult({}, "json_body_invalid")
        if not isinstance(body, dict):
            return _JsonParseResult({}, "json_body_invalid")
        return _JsonParseResult(body, None)

    def write_json(self, status: int, value: dict[str, Any]) -> None:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _template_for(path: str) -> str:
    if path.startswith("/api/now/table/incident/"):
        return "/api/now/table/incident/{sys_id}"
    return path


@dataclass(frozen=True)
class _JsonParseResult:
    body: dict[str, Any]
    error: str | None
