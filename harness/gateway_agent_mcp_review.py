"""Owner-facing review projection for frozen MCP agent admission."""
from __future__ import annotations

from .gateway_agent_mcp_admission import _validate_plan

REVIEW_SCHEMA = "flywheel.gateway-agent-mcp-admission-review/v1"


def review_mcp_admission(plan: dict | None) -> dict | None:
    if not plan:
        return None
    _validate_plan(plan)
    return {"schema": REVIEW_SCHEMA, "admission_sha256": plan["admission_sha256"],
        "servers": [_server(row) for row in plan["servers"]]}


def _server(server: dict) -> dict:
    launch = server["launch"]
    return {"server_id": server["server_id"],
        "catalog_ref": server["catalog_ref"],
        "timeout_s": server["timeout_s"],
        "descriptor_sha256": server["descriptor_sha256"],
        "config_sha256": server["config_sha256"],
        "tools_list_sha256": server["tools_list_sha256"],
        "discovery_receipt_sha256": server["discovery_receipt_sha256"],
        "cache_scope_sha256": server["cache_scope_sha256"],
        "launch": {"transport": launch["transport"],
            "inherit_env": launch["inherit_env"],
            "url_selected": bool(launch["url"]),
            "hide_window": launch["hide_window"],
            "allowed_tools": launch["allowed_tools"],
            "env_override_keys": [item[0] for item in launch["env_overrides"]]},
        "tools": [_tool(tool) for tool in server["tools"]]}


def _tool(tool: dict) -> dict:
    return {"source_tool_name": tool["source_tool_name"],
        "runtime_tool_name": tool["runtime_tool_name"],
        "input_schema_sha256": tool["input_schema_sha256"],
        "descriptor_sha256": tool["descriptor_sha256"],
        "declared_authority": tool["declared_authority"],
        "authority_source": tool["authority_source"],
        "enforced_limits": tool["enforced_limits"],
        "does_not_prove": tool["does_not_prove"]}
