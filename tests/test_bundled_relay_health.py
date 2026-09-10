import json


def _runtime(expected_version="0.2.0"):
    from harness.mcp_client import LaunchSpec

    class Runtime:
        name = "relay"
        blocking_codes = ()
        present = True
        installed_version = None
        launch = LaunchSpec(("relay-child",), allowed_tools=("relay.status",))

        def require_launch(self):
            return self.launch

        def to_dict(self, capability=None):
            return {
                "selected_runtime": "bundled",
                "capability": capability or {},
                "bundled_component": {
                    "descriptor_sha256": "sha256:" + "2" * 64,
                    "source_manifest_sha256": "sha256:" + "1" * 64,
                    "allowed_tools": ["relay.status"],
                },
            }

    runtime = Runtime()
    runtime.expected_version = expected_version
    return runtime


class _Client:
    def __init__(self, command, *, timeout, client_name, payload):
        self.server_info = {"name": "local-agent", "version": "0.2.0"}
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def list_tools(self):
        return [{"name": "relay.status", "inputSchema": {"type": "object"}}]

    def call_text(self, name, args):
        assert name == "relay.status"
        assert args == {}
        return self.payload


def _probe(monkeypatch, payload):
    import harness.mcp_client as mcp_client
    from harness import lanes

    monkeypatch.setattr(
        mcp_client, "MCPClient",
        lambda command, *, timeout, client_name: _Client(
            command, timeout=timeout, client_name=client_name,
            payload=payload),
    )
    return lanes._probe_lane("relay", None, 1, present=True,
                             runtime=_runtime())


def test_relay_status_inner_ok_false_is_not_live(monkeypatch):
    """Catches treating MCP envelope success as Relay health success."""
    from harness import lanes

    row = _probe(monkeypatch, {"ok": True, "text": json.dumps({
        "ok": False, "server": "relay", "version": "0.2.0"})})

    assert row["status"] == lanes.STALE
    assert "not healthy" in row["detail"]


def test_relay_status_invalid_json_is_not_live(monkeypatch):
    """Catches accepting non-JSON Relay health text."""
    from harness import lanes

    row = _probe(monkeypatch, {"ok": True, "text": "relay ok"})

    assert row["status"] == lanes.STALE
    assert "invalid JSON" in row["detail"]


def test_relay_status_wrong_server_or_version_is_not_live(monkeypatch):
    """Catches loss of source-bound Relay identity."""
    from harness import lanes

    wrong_server = _probe(monkeypatch, {"ok": True, "text": json.dumps({
        "ok": True, "server": "other", "version": "0.2.0"})})
    wrong_version = _probe(monkeypatch, {"ok": True, "text": json.dumps({
        "ok": True, "server": "relay", "version": "9.9.9"})})

    assert wrong_server["status"] == lanes.STALE
    assert wrong_version["status"] == lanes.STALE


def test_relay_status_inner_ok_true_with_matching_identity_is_live(monkeypatch):
    """Positive control for the admitted Relay status path."""
    from harness import lanes

    row = _probe(monkeypatch, {"ok": True, "text": json.dumps({
        "ok": True, "server": "relay", "version": "0.2.0"})})

    assert row["status"] == lanes.LIVE
