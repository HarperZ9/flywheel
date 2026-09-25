"""Backend-owned MCP discovery receipt cache for agent admission.

The cache is not part of an agent workspace. A caller can only reference a
receipt by owner/catalog/sha identity; it cannot provide arbitrary discovery
contents or a filesystem path for ``agent.run`` to trust.
"""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import time

from .credential_handles import CredentialBindings
from .evidence_json import canonical_sha256, strict_load_json
from .gateway_agent_mcp_authority import request_authority, validate_limits
from .gateway_agent_mcp_cache_io import _write_receipt
from .gateway_agent_mcp_cache_validation import (
    CACHE_DIR_NAME,
    DISCOVERY_RECEIPT_SCHEMA,
    _bounded_int,
    _catalog,
    _dedupe_notes,
    _digest,
    _discovery_policy,
    _effective_limits,
    _normalize_tools,
    _receipt_hash_material,
    _server,
    _server_info,
    _tool_names,
    freeze_receipt,
    receipt_path,
)
from .gateway_operation import GatewayOperationError
from .gateway_secret_boundary import validate_no_raw_secrets
from .journey_lock import JourneyLockBusy
from .mcp_client import LaunchSpec, MCPClient, MCPError
from .operation_grants import _secure_owner_only, _validate_owner_ref

DEFAULT_RECEIPT_MAX_AGE_S = 3600


def cache_mcp_discovery_receipt(
        catalog_ref: str, *, server_id: str, owner_ref: str, state_root: Path,
        tools: list[str] | tuple[str, ...], timeout_s: int,
        discovery_authorization: dict, client_factory=None,
        now: float | None = None) -> dict:
    """Launch one registered MCP server once and store a protected receipt.

    This is the explicit discovery startup boundary. ``agent.run`` prepare never
    calls this function implicitly; it only looks up a receipt written here.
    """
    try:
        owner = _validate_owner_ref(owner_ref)
        catalog = _catalog(catalog_ref)
        sid = _server(server_id)
        selected = _tool_names(tools)
        runtime_timeout = _bounded_int(timeout_s, 1, 60)
        startup_timeout = _discovery_policy(discovery_authorization, runtime_timeout)
        authority = request_authority(catalog, selected)
        launch, plugin_kind = restricted_catalog_launch(catalog, selected)
        limits = validate_limits(_effective_limits(launch))
        factory = client_factory or MCPClient
        client = factory(launch, timeout=startup_timeout,
                         client_name="flywheel-mcp-discovery-cache")
        try:
            client.start()
            tool_specs = _normalize_tools(client.list_tools(), selected)
            server_info = _server_info(getattr(client, "server_info", {}))
            protocol = str(getattr(client, "protocol_version", ""))
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        created = int(now if now is not None else time.time())
        launch_json = launch_to_json(launch)
        auth_rows = {name: authority[name]["authority"] for name in selected}
        notes = _dedupe_notes(
            note for name in selected for note in authority[name]["does_not_prove"])
        material = {
            "server_id": sid,
            "catalog_ref": catalog,
            "plugin_kind": plugin_kind,
            "selected_tools": selected,
            "launch": launch_json,
            "server_info": server_info,
            "protocol_version": protocol,
            "tools": tool_specs,
            "authority": auth_rows,
            "enforced_limits": limits,
        }
        receipt = {
            "schema": DISCOVERY_RECEIPT_SCHEMA,
            "owner_ref": owner,
            "catalog_ref": catalog,
            "server_id": sid,
            "plugin_kind": plugin_kind,
            "created_at_unix": created,
            "expires_at_unix": created + DEFAULT_RECEIPT_MAX_AGE_S,
            "timeout_s": runtime_timeout,
            "discovery_policy_sha256": canonical_sha256({
                "reason_present": True,
                "timeout_s": startup_timeout,
                "network": False,
            }),
            "selected_tools": selected,
            "credential_refs": [],
            "launch": launch_json,
            "launch_summary": launch_summary(launch),
            "server_info": server_info,
            "protocol_version": protocol,
            "tools": tool_specs,
            "authority": auth_rows,
            "authority_source": "gateway_catalog_metadata:v1",
            "enforced_limits": limits,
            "does_not_prove": notes,
            "tools_list_sha256": canonical_sha256({"tools": tool_specs}),
            "config_sha256": launch_config_sha256(catalog, plugin_kind, launch, selected),
            "descriptor_sha256": canonical_sha256(material),
        }
        receipt["receipt_sha256"] = canonical_sha256(_receipt_hash_material(receipt))
        validate_no_raw_secrets(receipt)
        freeze_receipt(receipt)
        _write_receipt(Path(state_root), owner, catalog, receipt)
        return receipt
    except GatewayOperationError:
        raise
    except JourneyLockBusy:
        raise GatewayOperationError("MCP_CACHE_UNAVAILABLE") from None
    except (OSError, PermissionError, TypeError, ValueError, MCPError):
        raise GatewayOperationError("MCP_DISCOVERY_RECEIPT_UNAVAILABLE") from None


def load_mcp_discovery_receipt(
        *, owner_ref: str, state_root: Path, catalog_ref: str, server_id: str,
        receipt_sha256: str, tools: list[str] | tuple[str, ...],
        timeout_s: int, now: float | None = None) -> dict:
    """Return one protected receipt after owner/catalog/freshness drift checks."""
    try:
        owner = _validate_owner_ref(owner_ref)
        catalog = _catalog(catalog_ref)
        sid = _server(server_id)
        selected = _tool_names(tools)
        runtime_timeout = _bounded_int(timeout_s, 1, 60)
        digest = _digest(receipt_sha256)
        path = receipt_path(Path(state_root), owner, catalog, digest)
        for parent in (path.parents[2], path.parents[1], path.parent):
            if not parent.is_dir():
                raise GatewayOperationError("MCP_DISCOVERY_RECEIPT_UNAVAILABLE")
            _secure_owner_only(parent, directory=True)
        _secure_owner_only(path, directory=False)
        receipt = strict_load_json(path.read_bytes(), max_bytes=131_072, max_depth=20)
        freeze_receipt(receipt)
        if (receipt["owner_ref"] != owner or receipt["catalog_ref"] != catalog
                or receipt["server_id"] != sid
                or receipt["receipt_sha256"] != digest
                or receipt["selected_tools"] != selected
                or receipt["timeout_s"] != runtime_timeout):
            raise GatewayOperationError("MCP_DISCOVERY_RECEIPT_UNAVAILABLE")
        current = int(now if now is not None else time.time())
        if current >= receipt["expires_at_unix"]:
            raise GatewayOperationError("MCP_DISCOVERY_RECEIPT_STALE")
        try:
            launch, plugin_kind = restricted_catalog_launch(catalog, selected)
            current_config = launch_config_sha256(catalog, plugin_kind, launch, selected)
        except GatewayOperationError as exc:
            if exc.code in {"CAPABILITY_NOT_ADMITTED", "MCP_CATALOG_LAUNCH_UNAVAILABLE",
                            "MCP_AMBIENT_ENV_UNSUPPORTED", "MCP_HTTP_TRANSPORT_UNSUPPORTED"}:
                raise GatewayOperationError("MCP_DISCOVERY_CONFIG_DRIFT") from None
            raise
        if (plugin_kind != receipt["plugin_kind"]
                or current_config != receipt["config_sha256"]
                or launch_to_json(launch) != receipt["launch"]):
            raise GatewayOperationError("MCP_DISCOVERY_CONFIG_DRIFT")
        return receipt
    except GatewayOperationError:
        raise
    except (OSError, PermissionError, TypeError, ValueError):
        raise GatewayOperationError("MCP_DISCOVERY_RECEIPT_UNAVAILABLE") from None


def restricted_catalog_launch(catalog_ref: str, tools: list[str] | tuple[str, ...]) -> tuple[LaunchSpec, str]:
    catalog = _catalog(catalog_ref)
    selected = tuple(_tool_names(tools))
    try:
        from .plugins import PluginPermissionError, _restricted_launch, plugin_execution_plan
        command, plugin_kind, slots, refs = plugin_execution_plan(catalog)
        if slots or refs:
            raise GatewayOperationError("MCP_CREDENTIAL_VERSION_UNAVAILABLE")
        launch = _restricted_launch(command, CredentialBindings({}), slots,
                                    lane=plugin_kind == "lane")
    except GatewayOperationError:
        raise
    except Exception:
        raise GatewayOperationError("MCP_CATALOG_LAUNCH_UNAVAILABLE") from None
    if not isinstance(launch, LaunchSpec):
        raise GatewayOperationError("MCP_CATALOG_LAUNCH_UNAVAILABLE")
    if launch.url:
        raise GatewayOperationError("MCP_HTTP_TRANSPORT_UNSUPPORTED")
    if launch.inherit_env:
        raise GatewayOperationError("MCP_AMBIENT_ENV_UNSUPPORTED")
    if launch.allowed_tools is not None and not set(selected) <= set(launch.allowed_tools):
        raise GatewayOperationError("CAPABILITY_NOT_ADMITTED")
    launch = _pin_catalog_cwd(launch)
    launch = replace(launch, allowed_tools=selected)
    validate_limits(_effective_limits(launch))
    validate_no_raw_secrets(launch_to_json(launch))
    return launch, str(plugin_kind or "mcp")


def _pin_catalog_cwd(launch: LaunchSpec) -> LaunchSpec:
    if launch.cwd:
        return launch
    root = _explicit_workspace_root()
    if root is None:
        raise GatewayOperationError("MCP_CATALOG_LAUNCH_UNAVAILABLE")
    return replace(launch, cwd=str(root))


def _explicit_workspace_root() -> Path | None:
    raw = os.environ.get("FLYWHEEL_WORKSPACE_ROOT", "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        return None
    try:
        root = candidate.resolve()
    except OSError:
        return None
    return root if root.is_dir() else None


def launch_to_json(launch: LaunchSpec) -> dict:
    return {
        "transport": "stdio",
        "argv": list(launch.argv),
        "cwd": launch.cwd,
        "env_overrides": [list(item) for item in launch.env_overrides],
        "inherit_env": launch.inherit_env,
        "url": launch.url,
        "hide_window": launch.hide_window,
        "allowed_tools": None if launch.allowed_tools is None else list(launch.allowed_tools),
    }


def launch_summary(launch: LaunchSpec) -> dict:
    try:
        from .lane_runtime_support import launch_summary as summary
        value = summary(launch)
    except Exception:
        value = {"argv_shape": ["arg0", *["arg" for _ in launch.argv[1:]]],
                 "cwd_selected": bool(launch.cwd),
                 "env_override_keys": sorted(key for key, _ in launch.env_overrides),
                 "inherit_env": launch.inherit_env, "url_selected": bool(launch.url),
                 "hide_window": launch.hide_window,
                 "allowed_tools": None if launch.allowed_tools is None else list(launch.allowed_tools)}
    return value


def launch_config_sha256(catalog_ref: str, plugin_kind: str, launch: LaunchSpec,
                         tools: list[str] | tuple[str, ...]) -> str:
    return canonical_sha256({
        "catalog_ref": catalog_ref,
        "plugin_kind": plugin_kind,
        "launch": launch_to_json(launch),
        "selected_tools": list(tools),
        "credential_refs": [],
    })
