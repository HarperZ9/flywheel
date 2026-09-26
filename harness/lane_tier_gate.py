"""The tool policy applied on each route that reaches a lane tool.

``lane_tool_policy`` says which tier each lane tool needs, which tools the
build leaves out and which arguments the engine forces. This module applies
that table where a call is made:

- ``/api/lane/<lane>/<tool>`` (``lane_caller.call_lane_tool``): the engine
  computes the tier; a granted T2 call widens the frozen launch for its one
  tool and that call only; a tool the build leaves out answers ``NOT_IN_BUILD``;
- Plugins (``plugins.call_plugin``): no tier travels with a plugin call, so a
  lane tool is reachable there only when the table lists it at T1;
- agent runs (``gateway_agent_mcp_cache.restricted_catalog_launch``): an agent
  may select a lane tool only when the table lists it at T1, in the build,
  with no argument guard, no state write and no open egress, since the agent
  runtime passes the model's arguments through and no inner call has a grant
  of its own (POLICY-DECISION C-11, C-12).

Argument guards apply on the lane call and Plugins routes: ``argument_refusal``
before anything spawns, then ``guard_args`` (allowlist, then forced values).
"""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from .lane_tool_policy import ID_PATTERN, guard_args, tool_policy

__all__ = ["admission_refusal", "agent_tool_refusal", "argument_refusal", "guard_args",
           "lane_policy_review", "not_in_build", "plugin_refusal", "widen_for_call"]


def not_in_build(lane: str, tool: str) -> dict[str, str]:
    """The fixed answer for a tool this build leaves out, with its reason slug."""
    entry = tool_policy(lane, tool)
    return {"code": "NOT_IN_BUILD", "error": "this build does not run this lane tool",
            "status": "unavailable", "name": lane, "tool": tool,
            "reason": entry.not_in_build if entry else ""}


def widen_for_call(launch: Any, lane: str, tool: str, granted_tier: str) -> Any:
    """The launch for one call: a granted T2 call admits its own T2 tool.

    Only a restricted launch changes, only for a tool the table lists at T2 and
    keeps in the build, and only when the call carries T2 or higher. The
    widened launch serves this call and is dropped with it."""
    allowed = getattr(launch, "allowed_tools", None)
    entry = tool_policy(lane, tool)
    if (allowed is None or tool in allowed or entry is None or entry.tier != "T2"
            or entry.not_in_build or granted_tier not in ("T2", "T3")):
        return launch
    return replace(launch, allowed_tools=(*allowed, tool))


def admission_refusal(launch: Any, lane: str, tool: str) -> dict | None:
    """None when the launch admits the tool; else the refusal to return."""
    from .mcp_client import capability_not_admitted, launch_allows_tool
    if launch_allows_tool(launch, tool):
        return None
    entry = tool_policy(lane, tool)
    if entry is not None and entry.not_in_build:
        return not_in_build(lane, tool)
    return capability_not_admitted(lane, tool)


def _plain_id(value: object) -> bool:
    return isinstance(value, str) and bool(ID_PATTERN.fullmatch(value)) and ".." not in value


def _reaches_home(lane: str, value: object, environ: Mapping[str, str]) -> bool:
    """True when a path argument resolves inside the Flywheel home, outside the
    lane's own folder. A relative path resolves from the lane folder, the
    child's working directory. A URL is not a local path."""
    from .lane_workdir import flywheel_home
    if not isinstance(value, str) or not value.strip() or "://" in value:
        return False
    home = flywheel_home(environ)
    own = home / "lanes" / lane
    try:
        raw = Path(os.path.expanduser(value.strip()))
        target = os.path.normcase(os.path.realpath(raw if raw.is_absolute() else own / raw))
    except (OSError, ValueError):
        return True   # an unresolvable path is refused, not guessed at
    home_s, own_s = (os.path.normcase(os.path.realpath(p)) for p in (home, own))
    return _inside(target, home_s) and not _inside(target, own_s)


def _inside(target: str, base: str) -> bool:
    return target == base or target.startswith(base.rstrip(os.sep) + os.sep)


def argument_refusal(lane: str, tool: str, args: Mapping[str, Any],
                     environ: Mapping[str, str] | None = None) -> dict | None:
    """None when the arguments pass the tool's id and path guards; else the
    fixed refusal, returned before any child spawns (C-4, C-14)."""
    entry = tool_policy(lane, tool)
    if entry is None:
        return None
    env = os.environ if environ is None else environ
    bad = any(name in args and not _plain_id(args[name]) for name in entry.id_args) or any(
        name in args and _reaches_home(lane, args[name], env) for name in entry.path_args)
    if not bad:
        return None
    return {"code": "LANE_TOOL_ERROR", "error": "the engine refused an argument of this "
            "lane tool", "status": "unavailable", "name": lane, "tool": tool,
            "reason": "argument_refused"}


def plugin_refusal(lane: str, tool: str) -> dict | None:
    """None when Plugins may call this lane tool; else the refusal.

    A plugin call carries no tier, so it runs at T1. A lane tool that needs more,
    or that the table does not list (C-11), is refused before anything is
    spawned, with the route that can carry it."""
    from .lane_caller import required_tier
    from .lanes_registry import LANES
    if lane not in LANES:
        return None
    required = required_tier(lane, tool)
    if required == "T1" and tool_policy(lane, tool) is not None:
        return None
    from .mcp_client import capability_not_admitted
    return {**capability_not_admitted(lane, tool), "required_tier": required,
            "route": "lane.call"}


def agent_tool_refusal(catalog: str, plugin_kind: str | None,
                       tools: tuple[str, ...] | list[str]) -> str | None:
    """None when an agent run may select every one of ``tools``; else a code."""
    from .lanes_registry import LANES
    if plugin_kind != "lane" or catalog not in LANES:
        return None
    from .lane_caller import required_tier
    for tool in tools:
        entry = tool_policy(catalog, tool)
        if (entry is None or required_tier(catalog, tool) != "T1" or entry.not_in_build
                or entry.guarded or entry.effect == "state_write" or entry.open_egress):
            return "CAPABILITY_NOT_ADMITTED"
    return None


def lane_policy_review(operation: Mapping[str, Any]) -> dict:
    """What a lane.call approval authorizes, for the owner's approval sheet
    (POLICY-DECISION C-13): the tier the tool needs and the tier requested,
    its effect and reason, what the engine forces or drops, and the arguments
    the child receives, in plain form. Raw secrets never reach an operation
    (``validate_no_raw_secrets``), so the arguments carry none."""
    from .lane_caller import required_tier
    lane, tool = str(operation.get("name", "")), str(operation.get("tool", ""))
    args = operation.get("args") if isinstance(operation.get("args"), Mapping) else {}
    entry = tool_policy(lane, tool)
    binds_key = bool(operation.get("credential_refs"))
    required = required_tier(lane, tool)
    if binds_key and required == "T1":
        required = "T2"   # the key rule (C-8)
    sent = guard_args(lane, tool, args)
    forced = {name: value for name, value in (entry.forced_args if entry else ())
              if value is not None}
    return {"lane": lane, "tool": tool, "listed": entry is not None,
            "required_tier": required,
            "requested_tier": str(operation.get("governance_tier") or "T1"),
            "t2": required != "T1", "binds_key": binds_key,
            "effect": entry.effect if entry else "", "reason": entry.reason if entry else "",
            "not_in_build": entry.not_in_build if entry else "",
            "forced_arguments": forced,
            "dropped_arguments": sorted(set(args) - set(sent)),
            "arguments": sent, "requested_arguments": dict(args)}

