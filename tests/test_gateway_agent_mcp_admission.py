import copy
from pathlib import Path
import sys
import time

import pytest

from harness.gateway_operation import GatewayOperationError, canonicalize_operation
from harness.gateway_agent_binding import freeze_agent_binding
from harness.plan_run_snapshot import thaw_json

OWNER = "owner_" + "a" * 32
OTHER_OWNER = "owner_" + "b" * 32
REPO = Path(__file__).resolve().parents[1]
POLICY = {"reason": "test bounded discovery", "timeout_s": 10, "network": False}


def _echo_schema(*, additional_properties=False, top_level_array=False):
    if top_level_array:
        return {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {"msg": {"type": "string"}},
        "required": ["msg"],
        "additionalProperties": additional_properties,
    }


def _echo_tool(tool_name="echo", *, schema=None):
    return {
        "name": tool_name,
        "description": "Echo a message.",
        "inputSchema": schema or _echo_schema(),
    }


def allow_synthetic_catalog(monkeypatch, *, tool_name="echo", schema=None,
                            authority=None, allowed=None):
    import harness.gateway_agent_mcp_authority as auth
    import harness.plugins as plugins
    from harness.mcp_client import LaunchSpec

    env = (("PYTHONPATH", str(REPO)), ("PYTHONSAFEPATH", "1"))
    selected = tuple(allowed or (tool_name,))
    launch = LaunchSpec(
        (sys.executable, "-m", "tests.synthetic_echo_mcp"),
        cwd=str(REPO), env_overrides=env, inherit_env=False,
        hide_window=True, allowed_tools=selected)
    original_plan = plugins.plugin_execution_plan

    def plan(name):
        if name == "synthetic":
            return launch, "lane", (), ()
        return original_plan(name)

    monkeypatch.setattr(plugins, "plugin_execution_plan", plan)
    auth_map = {
        "authority": authority or {
            "read": True, "write": False, "execute": False,
            "critical": False, "network": False,
        },
        "does_not_prove": [
            "catalog read-only metadata does not sandbox the MCP server process",
            "restricted launch pins argv, cwd, environment and tool allowlist but does not provide an OS network or filesystem sandbox",
        ],
    }
    monkeypatch.setitem(auth.TRUSTED_CATALOG_TOOL_METADATA, "synthetic", {tool_name: auth_map})
    if schema is not None or tool_name != "echo":
        class Client:
            def __init__(self, *_args, **_kwargs):
                self.server_info = {"name": "synthetic-stdio", "version": "1"}
                self.protocol_version = "2025-06-18"
            def start(self): return self
            def list_tools(self): return [_echo_tool(tool_name, schema=schema)]
            def call_text(self, _name, args):
                return {"ok": True, "text": "echo: " + str(args.get("msg", "")), "raw": {}}
            def close(self): pass
        return Client
    return None


def cache_synthetic_receipt(tmp_path, monkeypatch, *, tool_name="echo", schema=None,
                            authority=None, allowed=None):
    from harness.gateway_agent_mcp_cache import cache_mcp_discovery_receipt

    client_factory = allow_synthetic_catalog(
        monkeypatch, tool_name=tool_name, schema=schema,
        authority=authority, allowed=allowed)
    return cache_mcp_discovery_receipt(
        "synthetic", server_id="synthetic", owner_ref=OWNER,
        state_root=tmp_path / "state", tools=[tool_name], timeout_s=5,
        discovery_authorization=POLICY, client_factory=client_factory)


def agent_op(tmp_path, admission=None, *, tool_protocol=None, execution_mode=None,
             allow_write=False, allow_exec=False):
    root = tmp_path / "workspace"
    root.mkdir(exist_ok=True)
    op = {
        "goal": "use admitted mcp",
        "endpoint": "stub",
        "root": str(root),
        "max_steps": 3,
        "timeout_s": 30,
        "allow_write": allow_write,
        "allow_exec": allow_exec,
        "stream": True,
        "data_refs": [],
        "credential_refs": [],
    }
    if tool_protocol is not None:
        op["tool_protocol"] = tool_protocol
    if execution_mode is not None:
        op["execution_mode"] = execution_mode
    if admission is not None:
        op["mcp_admission"] = admission
    return op


def selection_admission(receipt, *, tools=None, timeout_s=None, credential_refs=None):
    server = {
        "server_id": receipt["server_id"],
        "catalog_ref": receipt["catalog_ref"],
        "receipt_sha256": receipt["receipt_sha256"],
        "tools": list(tools or receipt["selected_tools"]),
        "timeout_s": timeout_s or receipt["timeout_s"],
    }
    if credential_refs is not None:
        server["credential_refs"] = list(credential_refs)
    return {"schema": "flywheel.agent-run-mcp-admission-request/v1", "servers": [server]}


def caller_authored_admission():
    return {
        "schema": "flywheel.agent-run-mcp-admission-request/v1",
        "servers": [{
            "server_id": "synthetic",
            "tools": ["echo"],
            "timeout_s": 5,
            "discovery": {"mode": "cached", "server_info": {},
                          "protocol_version": "2025-06-18", "tools": [_echo_tool()]},
            "launch": {"transport": "catalog", "catalog_ref": "synthetic", "env_refs": []},
            "authority": {"echo": {"read": True, "write": False, "execute": False,
                                    "critical": False, "network": False}},
            "enforced_limits": {"no_shell": True, "pinned_cwd": True,
                                "inherit_env": False, "network_sandbox": False,
                                "filesystem_sandbox": False},
            "does_not_prove": ["caller-authored receipt is not authority"],
        }],
    }


def freeze_bound(op, tmp_path):
    return thaw_json(freeze_agent_binding(
        canonicalize_operation("agent.run", op), tmp_path / "workspace",
        owner_ref=OWNER, state_root=tmp_path / "state"))


def test_absent_mcp_preserves_v1_binding_and_default_denies_mcp(tmp_path):
    canonical = canonicalize_operation("agent.run", agent_op(tmp_path))
    binding = thaw_json(freeze_agent_binding(canonical, tmp_path / "workspace"))
    assert binding["schema"] == "flywheel.gateway-agent-binding/v1"
    assert binding["capabilities"] == {
        "allow_write": False,
        "allow_exec": False,
        "allow_mcp": False,
    }
    assert "mcp_admission" not in binding


def test_caller_supplied_discovery_and_authority_are_rejected_before_freeze(tmp_path):
    with pytest.raises(GatewayOperationError, match="INVALID_REQUEST"):
        canonicalize_operation("agent.run", agent_op(tmp_path, caller_authored_admission()))


def test_backend_cached_receipt_freezes_admission_and_preserves_no_mcp_v2(tmp_path, monkeypatch):
    compat = canonicalize_operation("agent.run", agent_op(tmp_path, tool_protocol="text"))
    compat_binding = thaw_json(freeze_agent_binding(compat, tmp_path / "workspace"))
    assert compat_binding["schema"] == "flywheel.gateway-agent-binding/v2"
    assert "mcp_admission" not in compat_binding
    assert compat_binding["capabilities"]["allow_mcp"] is False

    receipt = cache_synthetic_receipt(tmp_path, monkeypatch)
    binding = freeze_bound(agent_op(tmp_path, selection_admission(receipt), tool_protocol="text"), tmp_path)
    assert binding["schema"] == "flywheel.gateway-agent-binding/v3"
    assert binding["capabilities"]["allow_mcp"] is True
    admission = binding["mcp_admission"]
    assert admission["schema"] == "flywheel.gateway-agent-mcp-admission/v1"
    assert admission["request_sha256"]
    server = admission["servers"][0]
    assert server["discovery_receipt_sha256"] == receipt["receipt_sha256"]
    assert server["cache_scope_sha256"]
    assert server["tools"][0]["runtime_tool_name"] == "mcp_synthetic__echo"
    assert server["tools"][0]["declared_authority"]["read"] is True
    assert server["tools"][0]["enforced_limits"]["network_sandbox"] is False
    assert server["credential_refs"] == []


def test_hash_alone_cannot_authenticate_receipt_across_owner_scope(tmp_path, monkeypatch):
    receipt = cache_synthetic_receipt(tmp_path, monkeypatch)
    op = canonicalize_operation(
        "agent.run", agent_op(tmp_path, selection_admission(receipt)))
    with pytest.raises(GatewayOperationError, match="MCP_DISCOVERY_RECEIPT_UNAVAILABLE"):
        freeze_agent_binding(op, tmp_path / "workspace",
                             owner_ref=OTHER_OWNER, state_root=tmp_path / "state")


def test_current_catalog_config_drift_is_rejected_before_review(tmp_path, monkeypatch):
    receipt = cache_synthetic_receipt(tmp_path, monkeypatch)
    allow_synthetic_catalog(monkeypatch, allowed=("other",))
    op = canonicalize_operation("agent.run", agent_op(tmp_path, selection_admission(receipt)))
    with pytest.raises(GatewayOperationError, match="MCP_DISCOVERY_CONFIG_DRIFT"):
        freeze_agent_binding(op, tmp_path / "workspace",
                             owner_ref=OWNER, state_root=tmp_path / "state")


def test_unknown_catalog_authority_is_unavailable_before_launch(tmp_path, monkeypatch):
    from harness.gateway_agent_mcp_cache import cache_mcp_discovery_receipt

    launched = []
    class Client:
        def __init__(self, *_args, **_kwargs):
            launched.append(True)
    with pytest.raises(GatewayOperationError, match="MCP_AUTHORITY_UNAVAILABLE"):
        cache_mcp_discovery_receipt(
            "synthetic", server_id="synthetic", owner_ref=OWNER,
            state_root=tmp_path / "state", tools=["echo"], timeout_s=5,
            discovery_authorization=POLICY, client_factory=Client)
    assert launched == []


def test_write_authority_requires_allow_write_and_write_scope(tmp_path, monkeypatch):
    authority = {"read": True, "write": True, "execute": False,
                 "critical": False, "network": False}
    receipt = cache_synthetic_receipt(tmp_path, monkeypatch, authority=authority)
    op = canonicalize_operation("agent.run", agent_op(tmp_path, selection_admission(receipt)))
    assert "write" in op.scopes
    with pytest.raises(GatewayOperationError, match="CAPABILITY_NOT_ADMITTED"):
        freeze_agent_binding(op, tmp_path / "workspace",
                             owner_ref=OWNER, state_root=tmp_path / "state")
    freeze_bound(agent_op(tmp_path, selection_admission(receipt), allow_write=True), tmp_path)


def test_critical_authority_is_not_admitted_by_write_exec_flags(tmp_path, monkeypatch):
    authority = {"read": True, "write": False, "execute": False,
                 "critical": True, "network": False}
    receipt = cache_synthetic_receipt(tmp_path, monkeypatch, authority=authority)
    op = canonicalize_operation("agent.run", agent_op(
        tmp_path, selection_admission(receipt), allow_write=True, allow_exec=True))
    with pytest.raises(GatewayOperationError, match="MCP_CRITICAL_TOOL_UNSUPPORTED"):
        freeze_agent_binding(op, tmp_path / "workspace",
                             owner_ref=OWNER, state_root=tmp_path / "state")
