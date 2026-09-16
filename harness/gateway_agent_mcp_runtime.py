"""Runtime recheck and tool bridging for admitted agent-run MCP tools."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import time

from .gateway_agent_mcp_admission import (
    _freeze_tool, _server_runtime_fingerprint, _validate_plan,
)
from .gateway_operation import GatewayOperationError
from .mcp_client import LaunchSpec, MCPClient, MCPError


def prepare_mcp_runtime(plan: dict | None, *, live_admission: dict | None = None) -> dict:
    if not plan:
        return {"allow_mcp": False, "external": {}, "tools": []}
    _validate_plan(plan)
    if live_admission is not None:
        try:
            live_fingerprint = _runtime_fingerprint(live_admission)
        except Exception:
            raise GatewayOperationError("AGENT_MCP_RUNTIME_DRIFT")
        if live_fingerprint != _runtime_fingerprint(plan):
            raise GatewayOperationError("AGENT_MCP_RUNTIME_DRIFT")
    tools = [tool for server in plan["servers"] for tool in server["tools"]]
    return {"allow_mcp": True, "external": {}, "tools": tools,
            "mcp_admission_sha256": plan["admission_sha256"]}


@contextmanager
def open_mcp_runtime(plan: dict | None, *, credentials=None, root=None,
                     on_event=None, deadline=None):
    if not plan:
        yield {"allow_mcp": False, "external": {}, "tools": []}
        return
    _validate_plan(plan)
    with ExitStack() as stack:
        external, live_servers = {}, []
        for server in plan["servers"]:
            timeout = _remaining_timeout(server["timeout_s"], deadline)
            client = MCPClient(_launch_spec(server, credentials, root),
                               timeout=timeout,
                               client_name="flywheel-agent-mcp")
            stack.callback(client.close)
            client.start()
            live = _live_server(server, client.server_info,
                                getattr(client, "protocol_version", ""),
                                client.list_tools())
            if _server_runtime_fingerprint(live) != _server_runtime_fingerprint(server):
                raise GatewayOperationError("AGENT_MCP_RUNTIME_DRIFT")
            live_servers.append(_review_server(server))
            external.update(_external_tools(client, server, plan, deadline))
        if on_event:
            on_event({"type": "mcp_runtime_validated", "servers": live_servers})
        yield {"allow_mcp": True, "external": external,
               "tools": [t for s in plan["servers"] for t in s["tools"]],
               "mcp_admission_sha256": plan["admission_sha256"]}


def native_mcp_tool_schemas(plan: dict | None) -> list[dict]:
    if not plan:
        return []
    _validate_plan(plan)
    return [{"type": "function", "name": tool["runtime_tool_name"],
        "description": tool["description"], "strict": True,
        "parameters": tool["input_schema"]}
        for server in plan["servers"] for tool in server["tools"]]


def _runtime_fingerprint(plan: dict) -> str:
    from .evidence_json import canonical_sha256
    return canonical_sha256({"servers": [_server_runtime_material(s) for s in plan["servers"]]})


def _server_runtime_material(server: dict) -> dict:
    return {"server_id": server["server_id"], "server_info": server["server_info"],
        "protocol_version": server["protocol_version"], "tools": [{
            "source_tool_name": tool["source_tool_name"],
            "description": tool["description"],
            "input_schema": tool["input_schema"]} for tool in server["tools"]]}


def _launch_spec(server: dict, _credentials, _root) -> LaunchSpec:
    launch = server["launch"]
    return LaunchSpec(tuple(launch["argv"]), launch["cwd"],
        tuple(tuple(item) for item in launch["env_overrides"]),
        launch["inherit_env"], launch["url"], launch["hide_window"],
        tuple(tool["source_tool_name"] for tool in server["tools"]))


def _live_server(server: dict, server_info: dict, protocol_version: str,
                 tools: list[dict]) -> dict:
    if type(tools) is not list:
        raise GatewayOperationError("AGENT_MCP_RUNTIME_DRIFT")
    rows = []
    for tool in tools:
        if type(tool) is not dict or type(tool.get("name")) is not str:
            raise GatewayOperationError("AGENT_MCP_RUNTIME_DRIFT")
        rows.append(tool)
    names = [tool["name"] for tool in rows]
    if len(names) != len(set(names)):
        raise GatewayOperationError("AGENT_MCP_RUNTIME_DRIFT")
    by_name = {tool["name"]: tool for tool in rows}
    frozen = []
    for tool in server["tools"]:
        source = tool["source_tool_name"]
        if source not in by_name:
            raise GatewayOperationError("AGENT_MCP_RUNTIME_DRIFT")
        try:
            frozen.append(_freeze_tool({"server_id": server["server_id"],
                "authority": {source: tool["declared_authority"]},
                "enforced_limits": tool["enforced_limits"],
                "does_not_prove": tool["does_not_prove"]}, source, by_name[source]))
        except Exception:
            raise GatewayOperationError("AGENT_MCP_RUNTIME_DRIFT") from None
    return {"server_id": server["server_id"], "timeout_s": server["timeout_s"],
        "server_info": server_info, "protocol_version": protocol_version,
        "tools": frozen}


def _external_tools(client: MCPClient, server: dict, plan: dict, deadline) -> dict:
    out = {}
    for tool in server["tools"]:
        source, runtime = tool["source_tool_name"], tool["runtime_tool_name"]

        def _make(name):
            def fn(args):
                try:
                    _set_client_timeout(client, _remaining_timeout(
                        server["timeout_s"], deadline))
                except GatewayOperationError as exc:
                    return False, exc.code
                try:
                    result = client.call_text(name, args if isinstance(args, dict) else {})
                except MCPError as exc:
                    return False, str(exc)
                return result["ok"], result["text"]
            return fn

        out[runtime] = {"fn": _make(source), "description": tool["description"],
                        "admission": _admission_string(plan, server, tool),
                        "admission_metadata": _admission_metadata(plan, server, tool)}
    return out


def _review_server(server: dict) -> dict:
    return {"server_id": server["server_id"],
        "discovery_receipt_sha256": server.get("discovery_receipt_sha256", ""),
        "descriptor_sha256": server.get("descriptor_sha256", ""),
        "config_sha256": server.get("config_sha256", ""),
        "tools": [tool["runtime_tool_name"] for tool in server["tools"]]}


def _remaining_timeout(configured: int, deadline) -> float:
    if deadline is None:
        return float(configured)
    if type(deadline) not in (int, float):
        raise GatewayOperationError("OPERATION_DEADLINE_EXCEEDED")
    remaining = float(deadline) - time.monotonic()
    if remaining <= 0:
        raise GatewayOperationError("OPERATION_DEADLINE_EXCEEDED")
    return max(0.001, min(float(configured), remaining))


def _set_client_timeout(client: MCPClient, timeout: float) -> None:
    transport = getattr(client, "_t", None)
    if hasattr(transport, "timeout"):
        transport.timeout = timeout


def _admission_string(plan: dict, server: dict, tool: dict) -> str:
    return (
        "MCP_ADMITTED:"
        f"admission={plan['admission_sha256']}:"
        f"receipt={server['discovery_receipt_sha256']}:"
        f"server={server['descriptor_sha256']}:"
        f"tool={tool['descriptor_sha256']}"
    )


def _admission_metadata(plan: dict, server: dict, tool: dict) -> dict:
    return {
        "admission_sha256": plan["admission_sha256"],
        "discovery_receipt_sha256": server["discovery_receipt_sha256"],
        "server_descriptor_sha256": server["descriptor_sha256"],
        "tool_descriptor_sha256": tool["descriptor_sha256"],
        "config_sha256": server["config_sha256"],
    }
