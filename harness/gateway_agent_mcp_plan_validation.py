"""Frozen MCP admission plan validation and runtime fingerprints."""
from __future__ import annotations

import re

from .evidence_json import canonical_sha256
from .gateway_agent_mcp_authority import AUTHORITY_KEYS, validate_limits
from .gateway_operation import GatewayOperationError
from .journey_types import SHA256_PATTERN

ADMISSION_SCHEMA = "flywheel.gateway-agent-mcp-admission/v1"
_RAW_TOOL = re.compile(r"[^\s\x00-\x1f\x7f]{1,128}\Z")
_RUNTIME_TOOL = re.compile(r"[a-z]\w{0,63}\Z")
_CATALOG_REF = re.compile(r"[a-z][A-Za-z0-9_.-]{0,63}\Z")
_SERVER_ID = re.compile(r"[a-z][a-z0-9_]{0,23}\Z")
_SERVER_PLAN_KEYS = frozenset((
    "server_id", "catalog_ref", "timeout_s", "server_info",
    "protocol_version", "tools", "launch", "credential_refs",
    "discovery_receipt_sha256", "cache_scope_sha256", "tools_list_sha256",
    "config_sha256", "descriptor_sha256",
))
_TOOL_PLAN_KEYS = frozenset((
    "source_tool_name", "runtime_tool_name", "description", "input_schema",
    "declared_authority", "authority_source", "enforced_limits",
    "does_not_prove", "input_schema_sha256", "descriptor_sha256",
))


def _validate_plan(plan: object) -> None:
    if (type(plan) is not dict or plan.get("schema") != ADMISSION_SCHEMA
            or set(plan) != {"schema", "request_sha256", "servers", "admission_sha256"}
            or SHA256_PATTERN.fullmatch(plan.get("request_sha256", "")) is None):
        raise GatewayOperationError("AGENT_BINDING_DRIFT")
    if plan["admission_sha256"] != canonical_sha256(_hash_material(plan)):
        raise GatewayOperationError("AGENT_BINDING_DRIFT")
    try:
        if type(plan["servers"]) is not list or not plan["servers"]:
            raise ValueError
        ids = []
        for server in plan["servers"]:
            _validate_server_plan(server)
            ids.append(server["server_id"])
        if len(ids) != len(set(ids)):
            raise ValueError
        _reject_runtime_tool_collisions(plan["servers"])
    except Exception:
        raise GatewayOperationError("AGENT_BINDING_DRIFT") from None


def _validate_server_plan(server: object) -> None:
    if type(server) is not dict or set(server) != _SERVER_PLAN_KEYS:
        raise ValueError
    if (not _SERVER_ID.fullmatch(server.get("server_id", ""))
            or _CATALOG_REF.fullmatch(server.get("catalog_ref", "")) is None):
        raise ValueError
    _bounded_int(server.get("timeout_s"), 1, 60)
    if (type(server.get("server_info")) is not dict
            or type(server.get("protocol_version")) is not str
            or type(server.get("tools")) is not list or not server["tools"]
            or type(server.get("launch")) is not dict
            or server.get("credential_refs") != []):
        raise ValueError
    for key in ("discovery_receipt_sha256", "cache_scope_sha256", "tools_list_sha256",
                "config_sha256", "descriptor_sha256"):
        if SHA256_PATTERN.fullmatch(server.get(key, "")) is None:
            raise ValueError
    for tool in server["tools"]:
        _validate_tool_plan(tool)


def _validate_tool_plan(tool: object) -> None:
    if type(tool) is not dict or set(tool) != _TOOL_PLAN_KEYS:
        raise ValueError
    if (not _RAW_TOOL.fullmatch(tool.get("source_tool_name", ""))
            or _RUNTIME_TOOL.fullmatch(tool.get("runtime_tool_name", "")) is None
            or type(tool.get("description")) is not str
            or type(tool.get("input_schema")) is not dict
            or type(tool.get("declared_authority")) is not dict
            or set(tool["declared_authority"]) != AUTHORITY_KEYS
            or any(type(tool["declared_authority"][key]) is not bool
                   for key in AUTHORITY_KEYS)
            or tool.get("authority_source") != "gateway_catalog_metadata:v1"):
        raise ValueError
    validate_limits(tool.get("enforced_limits"))
    if (type(tool.get("does_not_prove")) is not list or not tool["does_not_prove"]
            or any(type(item) is not str or not item.strip()
                   or len(item) > 300 for item in tool["does_not_prove"])):
        raise ValueError
    if (tool["input_schema_sha256"] != canonical_sha256(tool["input_schema"])
            or SHA256_PATTERN.fullmatch(tool.get("descriptor_sha256", "")) is None):
        raise ValueError


def _hash_material(plan: dict) -> dict:
    return {k: v for k, v in plan.items() if k != "admission_sha256"}


def _server_runtime_fingerprint(server: dict) -> str:
    return canonical_sha256(_server_runtime_material(server))


def _server_runtime_material(server: dict) -> dict:
    return {"server_id": server["server_id"], "server_info": server["server_info"],
        "protocol_version": server["protocol_version"], "tools": [{
            "source_tool_name": tool["source_tool_name"],
            "description": tool["description"],
            "input_schema": tool["input_schema"]} for tool in server["tools"]]}


def _reject_runtime_tool_collisions(servers: list[dict]) -> None:
    names = [tool["runtime_tool_name"] for server in servers for tool in server["tools"]]
    if len(names) != len(set(names)):
        raise GatewayOperationError("AGENT_MCP_TOOL_COLLISION")


def _bounded_int(value: object, low: int, high: int) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError
