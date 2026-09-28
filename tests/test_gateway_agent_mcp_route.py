import json
import time

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_operation import canonicalize_operation
from harness.plan_run_snapshot import thaw_json
from tests.test_gateway_agent_mcp_admission import (
    OWNER,
    POLICY,
    agent_op,
    allow_synthetic_catalog,
    selection_admission,
)
from tests.test_gateway_agent_mcp_runtime_boundaries import pin_registered_index_workspace


def _error_code(body):
    return body.get("error", {}).get("code")


def test_catalog_route_lists_trusted_tools_without_starting_server(tmp_path, monkeypatch):
    """Catches a selector catalog GET that launches MCP before explicit discovery approval."""
    pin_registered_index_workspace(monkeypatch)
    started = []

    class Client:
        def __init__(self, *_args, **_kwargs):
            started.append(True)

    monkeypatch.setattr("harness.gateway_agent_mcp_cache.MCPClient", Client)
    from harness.gateway_agent_mcp_route import agent_mcp_get

    body, status = agent_mcp_get(
        "/api/agent/mcp/catalog", owner_ref=OWNER, state_root=tmp_path / "state")

    assert status == 200
    assert body["schema"] == "flywheel.agent-mcp-catalog/v1"
    assert started == []
    index = next(row for row in body["servers"] if row["catalog_ref"] == "index")
    assert index["server_id"] == "index"
    assert index["tools"][0]["source_tool_name"] == "index.doctor"
    assert index["tools"][0]["declared_authority"] == {
        "read": True,
        "write": False,
        "execute": False,
        "critical": False,
        "network": False,
    }
    assert index["availability"]["status"] == "available"
    assert not (tmp_path / "state" / "gateway-mcp-discovery-cache").exists()


def test_catalog_route_reports_unavailable_without_explicit_workspace_root(tmp_path, monkeypatch):
    """Catches route catalog tests that pass only because a host ambient root exists."""
    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOT", raising=False)
    from harness.gateway_agent_mcp_route import agent_mcp_get

    body, status = agent_mcp_get(
        "/api/agent/mcp/catalog", owner_ref=OWNER, state_root=tmp_path / "state")

    assert status == 200
    index = next(row for row in body["servers"] if row["catalog_ref"] == "index")
    assert index["availability"] == {
        "status": "unavailable",
        "code": "MCP_CATALOG_LAUNCH_UNAVAILABLE",
    }
    assert "launch" not in index
    assert not (tmp_path / "state" / "gateway-mcp-discovery-cache").exists()


def test_discovery_route_requires_explicit_start_authority(tmp_path, monkeypatch):
    """Catches a POST path that starts discovery from ordinary selector fields."""
    allow_synthetic_catalog(monkeypatch)
    from harness.gateway_agent_mcp_route import agent_mcp_post

    body, status = agent_mcp_post(
        "/api/agent/mcp/discovery-receipts",
        json.dumps({
            "schema": "flywheel.agent-mcp-discovery-request/v1",
            "server_id": "synthetic",
            "catalog_ref": "synthetic",
            "tools": ["echo"],
            "timeout_s": 5,
        }).encode("utf-8"),
        owner_ref=OWNER,
        state_root=tmp_path / "state",
    )

    assert status == 403
    assert _error_code(body) == "MCP_DISCOVERY_STARTUP_NOT_AUTHORIZED"
    assert not (tmp_path / "state" / "gateway-mcp-discovery-cache").exists()


def test_discovery_route_returns_selection_only_admission_and_freezes(tmp_path, monkeypatch):
    """Catches a product route that returns caller-authored discovery instead of a receipt reference."""
    allow_synthetic_catalog(monkeypatch)
    from harness.gateway_agent_mcp_route import agent_mcp_post

    body, status = agent_mcp_post(
        "/api/agent/mcp/discovery-receipts",
        json.dumps({
            "schema": "flywheel.agent-mcp-discovery-request/v1",
            "server_id": "synthetic",
            "catalog_ref": "synthetic",
            "tools": ["echo"],
            "timeout_s": 5,
            "discovery_authorization": POLICY,
        }).encode("utf-8"),
        owner_ref=OWNER,
        state_root=tmp_path / "state",
    )

    assert status == 200
    assert body["schema"] == "flywheel.agent-mcp-discovery-response/v1"
    admission = body["mcp_admission"]
    assert admission == {
        "schema": "flywheel.agent-run-mcp-admission-request/v1",
        "servers": [{
            "server_id": "synthetic",
            "catalog_ref": "synthetic",
            "receipt_sha256": body["receipt"]["receipt_sha256"],
            "tools": ["echo"],
            "timeout_s": 5,
        }],
    }
    assert set(admission["servers"][0]) == {
        "server_id", "catalog_ref", "receipt_sha256", "tools", "timeout_s"}
    assert body["receipt"]["launch"]["env_override_keys"] == ["PYTHONPATH", "PYTHONSAFEPATH"]
    binding = thaw_json(freeze_agent_binding(
        canonicalize_operation("agent.run", agent_op(tmp_path, admission)),
        tmp_path / "workspace", owner_ref=OWNER, state_root=tmp_path / "state"))
    assert binding["mcp_admission"]["servers"][0]["discovery_receipt_sha256"] == body["receipt"]["receipt_sha256"]


def test_real_index_doctor_route_roundtrip_uses_backend_receipt_lookup(tmp_path, monkeypatch):
    """Catches a UI route that is fixture-only and never proves a registered tool path."""
    workspace_root = pin_registered_index_workspace(monkeypatch)
    from harness.gateway_agent_mcp_admission import open_mcp_runtime
    from harness.gateway_agent_mcp_route import agent_mcp_post

    body, status = agent_mcp_post(
        "/api/agent/mcp/discovery-receipts",
        json.dumps({
            "schema": "flywheel.agent-mcp-discovery-request/v1",
            "server_id": "index",
            "catalog_ref": "index",
            "tools": ["index.doctor"],
            "timeout_s": 10,
            "discovery_authorization": {
                "reason": "user selected index.doctor for Rowan review",
                "timeout_s": 10,
                "network": False,
            },
        }).encode("utf-8"),
        owner_ref=OWNER,
        state_root=tmp_path / "state",
    )

    assert status == 200
    binding = thaw_json(freeze_agent_binding(
        canonicalize_operation("agent.run", agent_op(tmp_path, body["mcp_admission"])),
        tmp_path / "workspace", owner_ref=OWNER, state_root=tmp_path / "state"))
    assert binding["mcp_admission"]["servers"][0]["launch"]["cwd"] == workspace_root
    with open_mcp_runtime(binding["mcp_admission"], root=tmp_path / "workspace",
                          deadline=time.monotonic() + 20) as runtime:
        ok, text = runtime["external"]["mcp_index__index_doctor"]["fn"]({})
    assert ok is True
    assert "doctor" in text.lower()
    assert body["receipt"]["receipt_sha256"] == binding["mcp_admission"]["servers"][0]["discovery_receipt_sha256"]
