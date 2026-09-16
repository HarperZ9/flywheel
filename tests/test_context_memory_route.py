import io
import json

import harness.context_memory_route as route
import harness.gateway as gateway
from harness.context_memory_bridge import CAPTURE_SCHEMA, PREFLIGHT_SCHEMA
from harness.gateway_auth import load_or_create_token
from harness.gateway_custody import is_private

OWNER = "owner_" + "a" * 32
NOW = "2026-09-16T00:00:00Z"


class FakeBridge:
    def __init__(self):
        self.calls = []

    def health(self):
        return {"schema": "flywheel.context-memory-status/v1", "ok": True}

    def capture(self, owner_ref, req):
        self.calls.append(("capture", owner_ref, req))
        return {"schema": "flywheel.context-memory-capture/v1",
                "status": "stored", "owner_ref": owner_ref}

    def preflight(self, owner_ref, req):
        self.calls.append(("preflight", owner_ref, req))
        return {"schema": "flywheel.context-memory-preflight/v1",
                "status": "not_found_in_searched_sources",
                "hits": [],
                "does_not_prove": ["not_found does not mean never discussed"]}


def test_capture_and_preflight_route_to_same_backend_with_owner():
    bridge = FakeBridge()
    capture, capture_status = route.context_memory_post(
        "/api/context-memory/capture",
        json.dumps({"schema": CAPTURE_SCHEMA, "project_ref": "mission-memory",
                    "event": {"event_id": "turn-1"}}).encode(),
        owner_ref=OWNER, state_root="unused", clock=lambda: NOW, bridge=bridge)
    preflight, preflight_status = route.context_memory_post(
        "/api/context-memory/preflight",
        json.dumps({"schema": PREFLIGHT_SCHEMA, "project_ref": "mission-memory",
                    "query": "native bridge"}).encode(),
        owner_ref=OWNER, state_root="unused", clock=lambda: NOW, bridge=bridge)

    assert capture_status == 200 and capture["status"] == "stored"
    assert preflight_status == 200
    assert preflight["status"] == "not_found_in_searched_sources"
    assert [call[0] for call in bridge.calls] == ["capture", "preflight"]
    assert {call[1] for call in bridge.calls} == {OWNER}


def test_route_reports_bridge_errors_not_empty_results():
    class Failing(FakeBridge):
        def preflight(self, owner_ref, req):
            raise route.ContextMemoryError(
                "CANON_CONTEXT_TIMEOUT", "Canon context MCP timed out", 504)

    body, status = route.context_memory_post(
        "/api/context-memory/preflight",
        json.dumps({"schema": PREFLIGHT_SCHEMA, "project_ref": "mission-memory",
                    "query": "native bridge"}).encode(),
        owner_ref=OWNER, state_root="unused", clock=lambda: NOW, bridge=Failing())

    assert status == 504
    assert body["error"]["code"] == "CANON_CONTEXT_TIMEOUT"


def test_gateway_handler_dispatches_context_memory_post(monkeypatch, tmp_path):
    calls = []

    def fake_post(path, raw, *, owner_ref, state_root, clock):
        calls.append((path, raw, owner_ref, state_root))
        return {"ok": True}, 200

    monkeypatch.setattr(route, "context_memory_post", fake_post)
    monkeypatch.setattr(gateway._Handler, "owner_ref", OWNER, raising=False)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", tmp_path, raising=False)
    monkeypatch.setattr(gateway._Handler, "clock", lambda *a: NOW, raising=False)
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/context-memory/preflight"
    handler.rfile = io.BytesIO(json.dumps({
        "schema": PREFLIGHT_SCHEMA,
        "project_ref": "mission-memory",
        "query": "bridge",
    }).encode())
    handler.headers = {"Content-Length": str(len(handler.rfile.getvalue()))}
    sent = {}
    handler._json = lambda body, code=200: sent.update(body=body, code=code)

    gateway._Handler._post(handler)

    assert sent == {"body": {"ok": True}, "code": 200}
    assert calls[0][0] == "/api/context-memory/preflight"
    assert calls[0][2] == OWNER


def test_context_memory_http_auth_binds_private_owner(tmp_path):
    token = load_or_create_token(tmp_path)
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/context-memory/capture"
    handler.command = "POST"
    handler.auth_token = token
    handler.allowed_hosts = gateway.DEFAULT_HOSTS
    handler.flywheel_home = tmp_path
    handler.headers = {
        "Host": "localhost",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    assert is_private(handler.path)
    assert handler._authorized() is True
    assert handler.owner_ref.startswith("owner_")
