"""The tool policy applied on each route that reaches a lane tool.

``lane_tool_policy`` says which tier each lane tool needs, which tools the
build leaves out and which arguments the engine forces. This module applies
that table where a call is made:

- ``/api/lane/<lane>/<tool>`` (``lane_caller.call_lane_tool``): the engine
  computes the tier; a granted T2 call widens the frozen launch for its one
  tool and that call only; a tool the build leaves out answers ``NOT_IN_BUILD``;
- Plugins (``plugins.call_plugin``): no tier travels with a plugin call, so a
  lane tool is reachable there only when it needs T1;
- agent runs (``gateway_agent_mcp_cache.restricted_catalog_launch``): an agent
  may select a lane tool only when it needs T1, is in the build and carries no
  argument guard, since the agent runtime passes the model's arguments through.

Forced arguments (``guard_args``) apply on the lane call and Plugins routes.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from .lane_tool_policy import guard_args, tool_policy

__all__ = ["admission_refusal", "agent_tool_refusal", "guard_args", "not_in_build",
           "plugin_refusal", "widen_for_call"]


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


def plugin_refusal(lane: str, tool: str) -> dict | None:
    """None when Plugins may call this lane tool; else the refusal.

    A plugin call carries no tier, so it runs at T1. A lane tool that needs more
    is refused before anything is spawned, with the route that can carry it."""
    from .lane_caller import required_tier
    from .lanes_registry import LANES
    if lane not in LANES:
        return None
    required = required_tier(lane, tool)
    if required == "T1":
        return None
    from .mcp_client import capability_not_admitted
    return {**capability_not_admitted(lane, tool), "required_tier": required,
            "route": "lane.call"}


def agent_tool_refusal(catalog: str, plugin_kind: str | None,
                       tools: tuple[str, ...] | list[str]) -> str | None:
    """None when an agent run may select every one of ``tools``; else a code."""
    if plugin_kind != "lane":
        return None
    from .lane_caller import required_tier
    for tool in tools:
        entry = tool_policy(catalog, tool)
        if required_tier(catalog, tool) != "T1" or (
                entry is not None and (entry.not_in_build or entry.forced_args)):
            return "CAPABILITY_NOT_ADMITTED"
    return None

