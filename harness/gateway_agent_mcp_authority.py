"""Trusted MCP tool authority metadata for Rowan agent admission.

This module is intentionally small and operator-owned. MCP server annotations and
model-facing descriptions are not permission grants; they only describe a tool.
Admission uses this table to decide which registered catalog tools can be shown
for review and which grant scopes they require.
"""
from __future__ import annotations

from collections.abc import Mapping

from .gateway_operation import GatewayOperationError

AUTHORITY_KEYS = frozenset(("read", "write", "execute", "critical", "network"))
LIMIT_KEYS = frozenset((
    "no_shell", "pinned_cwd", "inherit_env",
    "network_sandbox", "filesystem_sandbox",
))

_NO_OS_SANDBOX_NOTE = (
    "restricted launch pins argv, cwd, environment and tool allowlist but does "
    "not provide an OS network or filesystem sandbox"
)
_DECLARED_AUTHORITY_NOTE = (
    "catalog authority describes the admitted tool contract; it does not prove "
    "the MCP server code cannot perform undeclared side effects"
)

TRUSTED_CATALOG_TOOL_METADATA: dict[str, dict[str, dict[str, object]]] = {
    "index": {
        "index.doctor": {
            "authority": {
                "read": True,
                "write": False,
                "execute": False,
                "critical": False,
                "network": False,
            },
            "does_not_prove": [
                _DECLARED_AUTHORITY_NOTE,
                _NO_OS_SANDBOX_NOTE,
            ],
        }
    }
}


def trusted_tool_metadata(catalog_ref: str, tool_name: str) -> dict[str, object]:
    try:
        metadata = TRUSTED_CATALOG_TOOL_METADATA[catalog_ref][tool_name]
        authority = _authority(metadata.get("authority"))
        notes = _notes(metadata.get("does_not_prove"))
    except GatewayOperationError:
        raise
    except Exception:
        raise GatewayOperationError("MCP_AUTHORITY_UNAVAILABLE") from None
    return {"authority": authority, "does_not_prove": notes,
            "authority_source": "gateway_catalog_metadata:v1"}


def request_authority(catalog_ref: str, tools: list[str] | tuple[str, ...]) -> dict[str, dict[str, object]]:
    return {name: trusted_tool_metadata(catalog_ref, name) for name in tools}


def trusted_catalog_selections() -> tuple[dict[str, object], ...]:
    """Return backend-owned selectable MCP metadata, never server annotations."""
    rows = []
    for catalog_ref in sorted(TRUSTED_CATALOG_TOOL_METADATA):
        tools = []
        for tool_name in sorted(TRUSTED_CATALOG_TOOL_METADATA[catalog_ref]):
            metadata = trusted_tool_metadata(catalog_ref, tool_name)
            tools.append({
                "source_tool_name": tool_name,
                "declared_authority": metadata["authority"],
                "authority_source": metadata["authority_source"],
                "does_not_prove": metadata["does_not_prove"],
            })
        rows.append({
            "server_id": catalog_ref,
            "catalog_ref": catalog_ref,
            "tools": tools,
        })
    return tuple(rows)


def mcp_tool_scopes(authority_rows) -> tuple[str, ...]:
    selected = set()
    for row in authority_rows:
        authority = row.get("authority") if isinstance(row, Mapping) else row
        if authority.get("write"):
            selected.add("write")
        if authority.get("execute"):
            selected.add("exec")
        if authority.get("network"):
            selected.add("network")
        if authority.get("critical"):
            selected.add("critical")
    return tuple(scope for scope in ("write", "exec", "network", "critical")
                 if scope in selected)


def enforce_effective_authority(
        authority: Mapping[str, bool], *, allow_write: bool, allow_exec: bool,
        operation_scopes: tuple[str, ...] | list[str] | set[str]) -> None:
    scopes = set(operation_scopes)
    if authority.get("critical"):
        raise GatewayOperationError("MCP_CRITICAL_TOOL_UNSUPPORTED")
    if authority.get("write") and (allow_write is not True or "write" not in scopes):
        raise GatewayOperationError("CAPABILITY_NOT_ADMITTED")
    if authority.get("execute") and (allow_exec is not True or "exec" not in scopes):
        raise GatewayOperationError("CAPABILITY_NOT_ADMITTED")
    if authority.get("network") and "network" not in scopes:
        raise GatewayOperationError("CAPABILITY_NOT_ADMITTED")


def validate_limits(limits: Mapping[str, bool]) -> dict[str, bool]:
    if type(limits) is not dict or set(limits) != LIMIT_KEYS:
        raise GatewayOperationError("MCP_CATALOG_LAUNCH_UNAVAILABLE")
    if any(type(limits[key]) is not bool for key in LIMIT_KEYS):
        raise GatewayOperationError("MCP_CATALOG_LAUNCH_UNAVAILABLE")
    if (limits["no_shell"] is not True or limits["pinned_cwd"] is not True
            or limits["inherit_env"] is not False
            or limits["network_sandbox"] is not False
            or limits["filesystem_sandbox"] is not False):
        raise GatewayOperationError("MCP_CATALOG_LAUNCH_UNAVAILABLE")
    return dict(limits)


def _authority(value: object) -> dict[str, bool]:
    if type(value) is not dict or set(value) != AUTHORITY_KEYS:
        raise GatewayOperationError("MCP_AUTHORITY_UNAVAILABLE")
    if any(type(value[key]) is not bool for key in AUTHORITY_KEYS):
        raise GatewayOperationError("MCP_AUTHORITY_UNAVAILABLE")
    return {key: bool(value[key]) for key in AUTHORITY_KEYS}


def _notes(value: object) -> list[str]:
    if (type(value) is not list or not value
            or any(type(item) is not str or not item.strip()
                   or len(item) > 300 for item in value)):
        raise GatewayOperationError("MCP_AUTHORITY_UNAVAILABLE")
    return [item for item in value]
