"""Validation helpers for backend-owned MCP discovery receipts."""
from __future__ import annotations

import re
from pathlib import Path

from .evidence_json import canonical_sha256
from .gateway_agent_mcp_authority import AUTHORITY_KEYS, validate_limits
from .gateway_operation import GatewayOperationError
from .journey_types import SHA256_PATTERN
from .mcp_client import LaunchSpec
from .operation_grants import _validate_owner_ref

DISCOVERY_RECEIPT_SCHEMA = "flywheel.gateway-mcp-discovery-receipt/v1"
CACHE_DIR_NAME = "gateway-mcp-discovery-cache"
_CATALOG_REF = re.compile(r"[a-z][A-Za-z0-9_.-]{0,63}\Z")
_SERVER_ID = re.compile(r"[a-z][a-z0-9_]{0,23}\Z")
_RAW_TOOL = re.compile(r"[^\s\x00-\x1f\x7f]{1,128}\Z")
_RECEIPT_FIELDS = frozenset((
    "schema", "owner_ref", "catalog_ref", "server_id", "plugin_kind",
    "created_at_unix", "expires_at_unix", "timeout_s",
    "discovery_policy_sha256", "selected_tools", "credential_refs",
    "launch", "launch_summary", "server_info", "protocol_version", "tools",
    "authority", "authority_source", "enforced_limits", "does_not_prove",
    "tools_list_sha256", "config_sha256", "descriptor_sha256",
    "receipt_sha256",
))

def freeze_receipt(value: object) -> None:
    if type(value) is not dict or set(value) != _RECEIPT_FIELDS:
        raise ValueError
    if (value.get("schema") != DISCOVERY_RECEIPT_SCHEMA
            or value.get("receipt_sha256") != canonical_sha256(_receipt_hash_material(value))):
        raise ValueError
    _validate_receipt_body(value)


def receipt_path(state_root: Path, owner_ref: str, catalog_ref: str, receipt_sha256: str) -> Path:
    owner = _validate_owner_ref(owner_ref)
    catalog = _catalog(catalog_ref)
    digest = _digest(receipt_sha256)
    return Path(state_root) / CACHE_DIR_NAME / owner / canonical_sha256(catalog) / f"{digest}.json"


def _receipt_hash_material(receipt: dict) -> dict:
    return {key: value for key, value in receipt.items() if key != "receipt_sha256"}


def _validate_receipt_body(value: dict) -> None:
    _validate_owner_ref(value.get("owner_ref"))
    _catalog(value.get("catalog_ref"))
    _server(value.get("server_id"))
    if type(value.get("plugin_kind")) is not str or not value["plugin_kind"]:
        raise ValueError
    if (type(value.get("created_at_unix")) is not int
            or type(value.get("expires_at_unix")) is not int
            or value["expires_at_unix"] <= value["created_at_unix"]):
        raise ValueError
    _bounded_int(value.get("timeout_s"), 1, 60)
    _digest(value.get("discovery_policy_sha256"))
    selected = _tool_names(value.get("selected_tools"))
    if value.get("credential_refs") != []:
        raise ValueError
    if (type(value.get("launch")) is not dict
            or type(value.get("launch_summary")) is not dict
            or type(value.get("server_info")) is not dict
            or type(value.get("protocol_version")) is not str):
        raise ValueError
    _normalize_tools(value.get("tools"), selected)
    if type(value.get("authority")) is not dict or set(value["authority"]) != set(selected):
        raise ValueError
    for item in value["authority"].values():
        if type(item) is not dict or set(item) != AUTHORITY_KEYS:
            raise ValueError
        if any(type(item[key]) is not bool for key in item):
            raise ValueError
    if value.get("authority_source") != "gateway_catalog_metadata:v1":
        raise ValueError
    validate_limits(value.get("enforced_limits"))
    if (type(value.get("does_not_prove")) is not list or not value["does_not_prove"]
            or any(type(item) is not str or not item.strip()
                   or len(item) > 300 for item in value["does_not_prove"])):
        raise ValueError
    for name in ("tools_list_sha256", "config_sha256", "descriptor_sha256"):
        _digest(value.get(name))
    if value["tools_list_sha256"] != canonical_sha256({"tools": value["tools"]}):
        raise ValueError


def _effective_limits(launch: LaunchSpec) -> dict[str, bool]:
    return {
        "no_shell": True,
        "pinned_cwd": bool(launch.cwd),
        "inherit_env": bool(launch.inherit_env),
        "network_sandbox": False,
        "filesystem_sandbox": False,
    }


def _normalize_tools(tools: object, selected: list[str]) -> list[dict]:
    if type(tools) is not list or not tools:
        raise ValueError
    rows = []
    for tool in tools:
        if (type(tool) is not dict or set(tool) - {"name", "description", "inputSchema"}
                or not _RAW_TOOL.fullmatch(tool.get("name", ""))
                or type(tool.get("description", "")) is not str
                or type(tool.get("inputSchema")) is not dict):
            raise ValueError
        rows.append({"name": tool["name"],
                     "description": str(tool.get("description", "")),
                     "inputSchema": tool["inputSchema"]})
    names = [tool["name"] for tool in rows]
    if len(names) != len(set(names)) or any(name not in names for name in selected):
        raise ValueError
    return [next(tool for tool in rows if tool["name"] == name) for name in selected]


def _discovery_policy(value: object, _runtime_timeout: int) -> int:
    if (type(value) is not dict or set(value) != {"reason", "timeout_s", "network"}
            or type(value.get("reason")) is not str or not value["reason"].strip()
            or value.get("network") is not False):
        raise GatewayOperationError("MCP_DISCOVERY_STARTUP_NOT_AUTHORIZED")
    return _bounded_int(value.get("timeout_s"), 1, 30)


def _server_info(value: object) -> dict:
    if type(value) is not dict:
        raise ValueError
    return {str(key): item for key, item in value.items()}


def _dedupe_notes(values) -> list[str]:
    out = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def _catalog(value: object) -> str:
    if type(value) is not str or _CATALOG_REF.fullmatch(value) is None:
        raise ValueError
    return value


def _server(value: object) -> str:
    if type(value) is not str or _SERVER_ID.fullmatch(value) is None:
        raise ValueError
    return value


def _tool_names(value: object) -> list[str]:
    if type(value) not in (list, tuple) or not value or len(value) > 32:
        raise ValueError
    if any(type(name) is not str or _RAW_TOOL.fullmatch(name) is None for name in value):
        raise ValueError
    if len(set(value)) != len(value):
        raise ValueError
    return list(value)


def _bounded_int(value: object, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError
    return value


def _digest(value: object) -> str:
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError
    return value
