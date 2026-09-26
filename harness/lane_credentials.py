"""Per-call provider keys for a lane child, through the credential_refs path.

The desktop stores provider keys in the OS keychain. An environment grant
(``env_allow`` in lanes.json) only forwards names present in the engine's own
environment, so a key saved in the app never reached a lane. This module binds
one saved key to one lane call:

  1. The ``lane.call`` operation names opaque ``credential_refs``. When the plan
     is frozen, before approval, each ref's slot name is read from handle
     metadata (never the value), and every name must be in that lane's
     ``env_allow`` grant. The frozen plan carries the names, so the approval
     covers which keys the call binds.
  2. After the grant is consumed, the gateway resolves the values
     (environment first, keychain second, ``keychain.resolve_credential``).
  3. At launch the grant is checked again, and the bound values join that one
     lane child's own environment (``plugin_launch._restricted_launch``). The
     engine's environment, other lanes and later calls never see them.
  4. The response is scrubbed of every bound value before it leaves the route.

An http lane spawns no child, so it binds nothing here; bulletin's signing key
keeps its own path.

The key rule (POLICY-DECISION C-8): binding a key makes a call T2
(``binds_any_key``), and a call below T2 has every key-shaped name the operator
granted through ``env_allow`` stripped from its child (``strip_key_grants``),
so ``mneme.remember`` or ``forum.plan`` at T1 runs key-free.
"""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Mapping

from .lane_env import BASE_NAMES, operator_grants
from .lane_workdir import spawns_lane_child
from .mcp_client import LaunchSpec

_BULLETIN_SIGNED_TOOLS = frozenset(("board_write_post", "board_publish_media_post"))
KEY_SHAPED = re.compile(
    r"(?:^|_)(?:API_?KEY|KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?|PAT)\Z")


def key_shaped(name: str) -> bool:
    """True for a variable name that names a credential by convention."""
    return bool(KEY_SHAPED.search(str(name).upper()))


def binds_any_key(bindings) -> bool:
    """True when a credential binding would hand this call a value."""
    try:
        return bool(_bound_values(bindings))
    except LaneCredentialError:
        return True


def strip_key_grants(lane_name: str, launch, registry: Mapping[str, object] | None = None):
    """The launch without the key-shaped names granted to this lane. An
    inheriting launch gets each one blanked, since it would inherit it."""
    if not isinstance(launch, LaunchSpec) or not spawns_lane_child(launch):
        return launch
    keys = {name.upper() for name in lane_key_grants(lane_name, registry) if key_shaped(name)}
    if not keys:
        return launch
    env = [(k, v) for k, v in launch.env_overrides if k.upper() not in keys]
    if launch.inherit_env:
        env += [(name, "") for name in sorted(keys)]
    return replace(launch, env_overrides=tuple(env))


class LaneCredentialError(RuntimeError):
    """A fixed refusal that names no slot and carries no value."""

    code = "PERMISSION_REQUIRED"

    def __init__(self) -> None:
        super().__init__(self.code)


def lane_key_grants(lane_name: str,
                    registry: Mapping[str, object] | None = None) -> tuple[str, ...]:
    """The key names the operator granted this lane (``env_allow``), without
    the base names every lane already gets."""
    if registry is None:
        from .lanes import read_registry
        try:
            registry = read_registry()
        except (OSError, ValueError):
            registry = {}   # an unreadable registry grants nothing
    row = registry.get(lane_name) if isinstance(registry, Mapping) else None
    names, _ = operator_grants(row if isinstance(row, Mapping) else {})
    return tuple(name for name in names if name.upper() not in BASE_NAMES)


def binds_lane_keys(operation) -> bool:
    """True for a lane.call that names refs outside bulletin's signing path."""
    value = operation.operation
    return (operation.action == "lane.call" and bool(value.get("credential_refs"))
            and not (value.get("name") == "bulletin"
                     and value.get("tool") in _BULLETIN_SIGNED_TOOLS))


def lane_call_credential_plan(operation, owner_ref: str | None,
                              state_root: Path | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(slot names, refs) for a keyed lane.call, read from metadata only."""
    from .credential_handles import CredentialHandleStore
    from .gateway_operation import GatewayOperationError
    from .lanes_registry import LANES
    value = operation.operation
    refs = tuple(value["credential_refs"])
    lane = LANES.get(value.get("name"))
    if lane is None or lane.kind == "http" or not owner_ref or state_root is None:
        raise GatewayOperationError("PERMISSION_REQUIRED")
    try:
        names = CredentialHandleStore(
            Path(state_root), keychain_get=lambda _slot: None,
        ).slot_names_exact(owner_ref, refs)
    except Exception:
        raise GatewayOperationError("PERMISSION_REQUIRED") from None
    granted = set(lane_key_grants(lane.name))
    if not names or any(name not in granted for name in names):
        raise GatewayOperationError("PERMISSION_REQUIRED")
    return tuple(names), refs


def bind_lane_credentials(lane_name: str, launch, bindings,
                          registry: Mapping[str, object] | None = None):
    """Return ``launch`` with the bound values joined, or raise
    LaneCredentialError when any bound name is not granted to this lane."""
    values = _bound_values(bindings)
    if not values:
        return launch
    granted = set(lane_key_grants(lane_name, registry))
    if (not isinstance(launch, LaunchSpec) or not spawns_lane_child(launch)
            or launch.inherit_env or any(name not in granted for name in values)):
        raise LaneCredentialError
    from .plugin_launch import PluginPermissionError, _restricted_launch
    try:
        return _restricted_launch(launch, bindings, tuple(values), lane=True)
    except PluginPermissionError:
        raise LaneCredentialError from None


def credential_refused(lane_name: str, tool_name: str) -> dict[str, str]:
    return {"code": LaneCredentialError.code,
            "error": "the bound credential is not granted to this lane",
            "status": "unavailable", "name": lane_name, "tool": tool_name}


def redact_result(result, bindings):
    """Scrub every bound value out of a lane result, at any depth."""
    if not _bound_values(bindings):
        return result
    return _redact(result, bindings)


def _redact(value, bindings):
    if isinstance(value, str):
        return bindings.redact(value)
    if isinstance(value, dict):
        return {_redact(key, bindings): _redact(item, bindings)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item, bindings) for item in value]
    return value


def _bound_values(bindings) -> dict[str, str]:
    if bindings is None:
        return {}
    try:
        return bindings.child_environment({}, platform="windows")
    except Exception:
        raise LaneCredentialError from None
