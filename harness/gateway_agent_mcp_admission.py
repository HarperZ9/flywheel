"""Exact MCP server/tool admission for bound ``agent.run`` operations."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re

from .evidence_json import canonical_sha256
from .gateway_agent_mcp_authority import (
    enforce_effective_authority,
    mcp_tool_scopes,
    request_authority,
    validate_limits,
)
from .gateway_agent_mcp_plan_validation import (
    _hash_material,
    _reject_runtime_tool_collisions,
    _server_runtime_fingerprint,
    _server_runtime_material,
    _validate_plan,
)
from .gateway_operation import CREDENTIAL_REF_PATTERN, GatewayOperationError
from .gateway_secret_boundary import validate_no_raw_secrets
from .journey_types import SHA256_PATTERN
from .local_tools import ToolExecutor
from .plan_run_snapshot import freeze_json

REQUEST_SCHEMA = "flywheel.agent-run-mcp-admission-request/v1"
ADMISSION_SCHEMA = "flywheel.gateway-agent-mcp-admission/v1"
_SERVER_ID = re.compile(r"[a-z][a-z0-9_]{0,23}\Z")
_RAW_TOOL = re.compile(r"[^\s\x00-\x1f\x7f]{1,128}\Z")
_RUNTIME_TOOL = re.compile(r"[a-z]\w{0,63}\Z")
_CATALOG_REF = re.compile(r"[a-z][A-Za-z0-9_.-]{0,63}\Z")
_DESC_LIMIT = 300
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


def validate_mcp_admission_request(value: object) -> None:
    _request_servers(value)


def mcp_admission_request_scopes(value: object) -> tuple[str, ...]:
    scopes = []
    for server in _request_servers(value):
        for row in request_authority(server["catalog_ref"], server["tools"]).values():
            scopes.extend(mcp_tool_scopes((row,)))
    return tuple(scope for scope in ("write", "exec", "network", "critical")
                 if scope in set(scopes))


def freeze_mcp_admission(
        value: object | None, workspace_root: Path, *, owner_ref: str | None = None,
        state_root: Path | None = None, operation=None) -> dict | None:
    if value is None:
        return None
    if type(owner_ref) is not str or state_root is None:
        raise GatewayOperationError("MCP_DISCOVERY_RECEIPT_UNAVAILABLE")
    servers = [_freeze_server(row, owner_ref=owner_ref, state_root=Path(state_root),
                              operation=operation)
               for row in _request_servers(value)]
    _reject_runtime_tool_collisions(servers)
    plan = {"schema": ADMISSION_SCHEMA,
            "request_sha256": canonical_sha256(_plain(value)),
            "servers": servers}
    plan["admission_sha256"] = canonical_sha256(_hash_material(plan))
    freeze_json(plan, max_bytes=65536)
    _validate_plan(plan)
    return plan


def validate_mcp_admission_plan(plan: object, request: object | None = None) -> None:
    _validate_plan(plan)
    if request is not None and plan["request_sha256"] != canonical_sha256(_plain(request)):
        raise GatewayOperationError("AGENT_BINDING_DRIFT")


def prepare_mcp_runtime(plan: dict | None, *, live_admission: dict | None = None) -> dict:
    from .gateway_agent_mcp_runtime import prepare_mcp_runtime as prepare
    return prepare(plan, live_admission=live_admission)


def open_mcp_runtime(plan: dict | None, *, credentials=None, root=None, on_event=None,
                     deadline=None):
    from .gateway_agent_mcp_runtime import open_mcp_runtime as open_runtime
    return open_runtime(plan, credentials=credentials, root=root,
                        on_event=on_event, deadline=deadline)


def native_mcp_tool_schemas(plan: dict | None) -> list[dict]:
    from .gateway_agent_mcp_runtime import native_mcp_tool_schemas as schemas
    return schemas(plan)


def _request_servers(value: object) -> list[dict]:
    value = _plain(value)
    if (type(value) is not dict or value.get("schema") != REQUEST_SCHEMA
            or set(value) != {"schema", "servers"}
            or type(value.get("servers")) is not list or not value["servers"]):
        raise ValueError
    servers = value["servers"]
    if len(servers) > 8:
        raise ValueError
    ids = []
    for server in servers:
        _validate_request_server(server)
        ids.append(server["server_id"])
    if len(set(ids)) != len(ids):
        raise ValueError
    return servers


def _plain(value: object):
    if isinstance(value, Mapping):
        return {str(key): _plain(child) for key, child in value.items()}
    if type(value) in (list, tuple):
        return [_plain(child) for child in value]
    return value


def _validate_request_server(server: object) -> None:
    if type(server) is not dict:
        raise ValueError
    allowed = {"server_id", "catalog_ref", "tools", "timeout_s",
               "receipt_sha256", "credential_refs"}
    if set(server) - allowed or not _SERVER_ID.fullmatch(server.get("server_id", "")):
        raise ValueError
    if _CATALOG_REF.fullmatch(server.get("catalog_ref", "")) is None:
        raise ValueError
    _bounded_int(server.get("timeout_s"), 1, 60)
    _tool_names(server.get("tools"))
    if SHA256_PATTERN.fullmatch(server.get("receipt_sha256", "")) is None:
        raise ValueError
    refs = server.get("credential_refs", [])
    if type(refs) is not list or any(
            type(ref) is not str or CREDENTIAL_REF_PATTERN.fullmatch(ref) is None
            for ref in refs):
        raise ValueError
    if refs:
        raise GatewayOperationError("MCP_CREDENTIAL_VERSION_UNAVAILABLE")
    request_authority(server["catalog_ref"], server["tools"])


def _freeze_server(server: dict, *, owner_ref: str, state_root: Path,
                   operation) -> dict:
    from .gateway_agent_mcp_cache import load_mcp_discovery_receipt
    selected = _tool_names(server["tools"])
    receipt = load_mcp_discovery_receipt(
        owner_ref=owner_ref, state_root=state_root,
        catalog_ref=server["catalog_ref"], server_id=server["server_id"],
        receipt_sha256=server["receipt_sha256"], tools=selected,
        timeout_s=server["timeout_s"])
    authority_rows = request_authority(server["catalog_ref"], selected)
    allow_write, allow_exec, scopes = _operation_permissions(operation)
    discovered = {tool["name"]: tool for tool in receipt["tools"]}
    frozen_tools = []
    for name in selected:
        metadata = authority_rows[name]
        enforce_effective_authority(metadata["authority"], allow_write=allow_write,
                                    allow_exec=allow_exec, operation_scopes=scopes)
        frozen_tools.append(_freeze_tool({
            "server_id": server["server_id"],
            "authority": {name: metadata["authority"]},
            "authority_source": metadata["authority_source"],
            "enforced_limits": receipt["enforced_limits"],
            "does_not_prove": metadata["does_not_prove"],
        }, name, discovered[name]))
    material = {"server_id": server["server_id"], "tools": frozen_tools,
        "launch": receipt["launch"], "server_info": receipt["server_info"],
        "protocol_version": receipt["protocol_version"]}
    frozen = {"server_id": server["server_id"],
        "catalog_ref": server["catalog_ref"],
        "timeout_s": server["timeout_s"],
        "server_info": receipt["server_info"],
        "protocol_version": receipt["protocol_version"],
        "tools": frozen_tools,
        "launch": receipt["launch"],
        "credential_refs": [],
        "discovery_receipt_sha256": receipt["receipt_sha256"],
        "cache_scope_sha256": canonical_sha256({
            "owner_ref": owner_ref, "catalog_ref": server["catalog_ref"],
            "receipt_sha256": receipt["receipt_sha256"]}),
        "tools_list_sha256": canonical_sha256(_server_runtime_material(material)),
        "config_sha256": receipt["config_sha256"],
        "descriptor_sha256": canonical_sha256(material)}
    validate_limits(receipt["enforced_limits"])
    validate_no_raw_secrets(frozen)
    return frozen


def _operation_permissions(operation) -> tuple[bool, bool, tuple[str, ...]]:
    if operation is None:
        return False, False, ()
    value = getattr(operation, "operation", operation)
    scopes = getattr(operation, "scopes", ())
    return (value.get("allow_write") is True,
            value.get("allow_exec") is True,
            tuple(scopes))


def _freeze_tool(server: dict, name: str, tool: dict) -> dict:
    runtime = _runtime_tool_name(server["server_id"], name)
    if runtime in ToolExecutor._BUILTIN_CAPABILITY:
        raise GatewayOperationError("AGENT_MCP_TOOL_SHADOWS_BUILTIN")
    frozen = {"source_tool_name": name, "runtime_tool_name": runtime,
        "description": str(tool.get("description", ""))[:_DESC_LIMIT],
        "input_schema": tool["inputSchema"],
        "declared_authority": server["authority"][name],
        "authority_source": server.get("authority_source", "gateway_catalog_metadata:v1"),
        "enforced_limits": server["enforced_limits"],
        "does_not_prove": list(server["does_not_prove"])}
    frozen["input_schema_sha256"] = canonical_sha256(frozen["input_schema"])
    frozen["descriptor_sha256"] = canonical_sha256({
        "source_tool_name": frozen["source_tool_name"],
        "runtime_tool_name": frozen["runtime_tool_name"],
        "description": frozen["description"],
        "input_schema_sha256": frozen["input_schema_sha256"],
        "declared_authority": frozen["declared_authority"],
        "authority_source": frozen["authority_source"],
        "enforced_limits": frozen["enforced_limits"],
    })
    return frozen


def _tool_names(value: object) -> list[str]:
    if type(value) is not list or not value or len(value) > 32:
        raise ValueError
    if any(type(name) is not str or _RAW_TOOL.fullmatch(name) is None for name in value):
        raise ValueError
    if len(set(value)) != len(value):
        raise ValueError
    return list(value)


def _runtime_tool_name(server_id: str, source_tool_name: str) -> str:
    suffix = re.sub(r"\W+", "_", source_tool_name).strip("_").lower()
    if not suffix:
        raise ValueError
    name = f"mcp_{server_id}__{suffix[:28]}"
    if _RUNTIME_TOOL.fullmatch(name) is None:
        raise ValueError
    return name


def _bounded_int(value: object, low: int, high: int) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError
