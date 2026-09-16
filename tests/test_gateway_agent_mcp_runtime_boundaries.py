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


def pin_registered_index_workspace(monkeypatch):
    """Use an explicit, existing workspace root for registered package-lane tests."""
    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOT", raising=False)
    assert REPO.is_absolute() and REPO.is_dir()
    root = str(REPO.resolve())
    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOT", root)
    return root


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


def test_native_prepare_rejects_mcp_schema_unsupported_before_provider(tmp_path, monkeypatch):
    receipt = cache_synthetic_receipt(
        tmp_path, monkeypatch, schema=_echo_schema(additional_properties=True))
    operation = agent_op(tmp_path, selection_admission(receipt), tool_protocol="native")
    operation.update(endpoint="openai", model="gpt-6-astra", max_tokens=128)
    with pytest.raises(GatewayOperationError, match="AGENT_MCP_SCHEMA_UNSUPPORTED"):
        freeze_agent_binding(canonicalize_operation("agent.run", operation),
                             tmp_path / "workspace", owner_ref=OWNER,
                             state_root=tmp_path / "state")


def test_runtime_revalidation_rejects_live_schema_drift_before_tool_map(tmp_path, monkeypatch):
    from harness.gateway_agent_mcp_admission import prepare_mcp_runtime

    receipt = cache_synthetic_receipt(tmp_path, monkeypatch)
    binding = freeze_bound(agent_op(tmp_path, selection_admission(receipt)), tmp_path)
    live = copy.deepcopy(binding["mcp_admission"])
    live["servers"][0]["tools"][0]["input_schema"] = {
        "type": "object",
        "properties": {"changed": {"type": "string"}},
        "required": ["changed"],
        "additionalProperties": False,
    }

    with pytest.raises(GatewayOperationError, match="AGENT_MCP_RUNTIME_DRIFT"):
        prepare_mcp_runtime(binding["mcp_admission"], live_admission=live)


def test_runtime_revalidation_rejects_malformed_and_duplicate_live_tools_before_provider(tmp_path, monkeypatch):
    from harness.gateway_agent_mcp_admission import open_mcp_runtime

    receipt = cache_synthetic_receipt(tmp_path, monkeypatch)
    binding = freeze_bound(agent_op(tmp_path, selection_admission(receipt)), tmp_path)

    class Client:
        def __init__(self, *_args, **_kwargs):
            self.server_info = {"name": "synthetic-stdio", "version": "1"}
            self.protocol_version = "2025-06-18"
        def start(self): return self
        def list_tools(self):
            tool = _echo_tool()
            return [tool, dict(tool), "malformed"]
        def close(self): pass

    monkeypatch.setattr("harness.gateway_agent_mcp_runtime.MCPClient", Client)
    with pytest.raises(GatewayOperationError, match="AGENT_MCP_RUNTIME_DRIFT"):
        with open_mcp_runtime(binding["mcp_admission"], root=tmp_path / "workspace"):
            pass


def test_runtime_tool_name_collision_is_rejected_in_frozen_plan(tmp_path, monkeypatch):
    from harness.gateway_agent_mcp_cache import cache_mcp_discovery_receipt
    import harness.gateway_agent_mcp_authority as auth

    authority = {"read": True, "write": False, "execute": False,
                 "critical": False, "network": False}
    notes = ["catalog read-only metadata does not sandbox the MCP server process"]
    allow_synthetic_catalog(monkeypatch, tool_name="a-b", allowed=("a-b", "a_b"))
    auth.TRUSTED_CATALOG_TOOL_METADATA["synthetic"]["a_b"] = {
        "authority": authority, "does_not_prove": notes}

    class Client:
        def __init__(self, *_args, **_kwargs):
            self.server_info = {"name": "synthetic-stdio", "version": "1"}
            self.protocol_version = "2025-06-18"
        def start(self): return self
        def list_tools(self):
            return [_echo_tool("a-b"), _echo_tool("a_b")]
        def close(self): pass

    receipt = cache_mcp_discovery_receipt(
        "synthetic", server_id="synthetic", owner_ref=OWNER,
        state_root=tmp_path / "state", tools=["a-b", "a_b"], timeout_s=5,
        discovery_authorization=POLICY, client_factory=Client)
    op = canonicalize_operation("agent.run", agent_op(tmp_path, selection_admission(receipt)))
    with pytest.raises(GatewayOperationError, match="AGENT_MCP_TOOL_COLLISION"):
        freeze_agent_binding(op, tmp_path / "workspace",
                             owner_ref=OWNER, state_root=tmp_path / "state")


def test_credential_bearing_admission_fails_without_version_pin(tmp_path, monkeypatch):
    receipt = cache_synthetic_receipt(tmp_path, monkeypatch)
    with pytest.raises(GatewayOperationError, match="MCP_CREDENTIAL_VERSION_UNAVAILABLE"):
        canonicalize_operation("agent.run", agent_op(
            tmp_path, selection_admission(receipt, credential_refs=["cred_" + "c" * 32])))


def test_native_cli_session_rejects_mcp_admission(tmp_path, monkeypatch):
    receipt = cache_synthetic_receipt(tmp_path, monkeypatch)
    with pytest.raises(GatewayOperationError, match="INVALID_REQUEST"):
        canonicalize_operation(
            "agent.run",
            agent_op(
                tmp_path,
                selection_admission(receipt),
                execution_mode="native_cli_session",
                tool_protocol=None,
            ),
        )


def test_real_registered_index_doctor_roundtrip_uses_restricted_catalog_launch(tmp_path, monkeypatch):
    from harness.gateway_agent_mcp_cache import cache_mcp_discovery_receipt
    from harness.gateway_agent_mcp_admission import open_mcp_runtime

    workspace_root = pin_registered_index_workspace(monkeypatch)
    receipt = cache_mcp_discovery_receipt(
        "index", server_id="index", owner_ref=OWNER,
        state_root=tmp_path / "state", tools=["index.doctor"], timeout_s=10,
        discovery_authorization=POLICY)
    binding = freeze_bound(agent_op(tmp_path, selection_admission(receipt)), tmp_path)
    server = binding["mcp_admission"]["servers"][0]
    assert server["launch"]["cwd"] == workspace_root
    assert server["launch"]["inherit_env"] is False
    assert server["launch"]["allowed_tools"] == ["index.doctor"]
    assert "SYSTEMROOT" in dict(server["launch"]["env_overrides"]) or sys.platform != "win32"

    with open_mcp_runtime(binding["mcp_admission"], root=tmp_path / "workspace",
                          deadline=time.monotonic() + 20) as runtime:
        spec = runtime["external"]["mcp_index__index_doctor"]
        ok, text = spec["fn"]({})
    assert ok is True
    assert "doctor" in text.lower()
    assert receipt["config_sha256"] == server["config_sha256"]
