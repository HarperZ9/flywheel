import io
import json

from harness import gateway
from harness.gateway_custody import is_private
from tests.test_gateway_agent_mcp_admission import OWNER, POLICY, allow_synthetic_catalog


class _Headers:
    def __init__(self, raw: bytes, *, content_length=None):
        self.raw = raw
        self.content_length = str(len(raw)) if content_length is None else content_length

    def get(self, key, default=None):
        if key == "Content-Length":
            return self.content_length
        return default


def _handler(tmp_path, path: str, raw=b"{}", *, content_length=None):
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.owner_ref = OWNER
    h.flywheel_home = tmp_path
    h.root = tmp_path
    h.run_root = str(tmp_path)
    h.clock = lambda: "2026-09-15T12:00:00Z"
    h.headers = _Headers(raw, content_length=content_length)
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda body, code=200: sent.update(body=body, code=code)
    return h, sent


def test_mcp_gateway_hooks_are_private_and_read_catalog_without_launch(tmp_path, monkeypatch):
    assert is_private("/api/agent/mcp/catalog")
    started = []

    class Client:
        def __init__(self, *_args, **_kwargs):
            started.append(True)

    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOT", "C:/dev")
    monkeypatch.setattr("harness.gateway_agent_mcp_cache.MCPClient", Client)
    h, sent = _handler(tmp_path, "/api/agent/mcp/catalog")

    h._get()

    assert sent["code"] == 200
    assert sent["body"]["schema"] == "flywheel.agent-mcp-catalog/v1"
    assert started == []


def test_mcp_gateway_post_rejects_invalid_content_length(tmp_path):
    assert is_private("/api/agent/mcp/discovery-receipts")
    h, sent = _handler(
        tmp_path, "/api/agent/mcp/discovery-receipts", b"{}",
        content_length="-1")

    h._post()

    assert sent["code"] == 400
    assert sent["body"]["error"]["code"] == "INVALID_LENGTH"


def test_mcp_gateway_post_routes_authorized_discovery(tmp_path, monkeypatch):
    allow_synthetic_catalog(monkeypatch)
    raw = json.dumps({
        "schema": "flywheel.agent-mcp-discovery-request/v1",
        "server_id": "synthetic",
        "catalog_ref": "synthetic",
        "tools": ["echo"],
        "timeout_s": 5,
        "discovery_authorization": POLICY,
    }).encode("utf-8")
    h, sent = _handler(tmp_path, "/api/agent/mcp/discovery-receipts", raw)

    h._post()

    assert sent["code"] == 200
    assert sent["body"]["schema"] == "flywheel.agent-mcp-discovery-response/v1"
    assert sent["body"]["mcp_admission"]["servers"][0]["receipt_sha256"]
