"""lane_caller.py -- generic MCP lane caller for the gateway.

Generalizes _forum_mcp_call: spawns any registered lane's MCP server, calls
the named tool, and returns the parsed JSON. Gated by the governance envelope's
tier check (a T1-classified run cannot call tools that require T2+ authority).
"""
from __future__ import annotations

import json
from typing import Any


def call_lane_tool(
    lane_name: str,
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    timeout: int = 20,
    governance_tier: str = "",
) -> dict[str, Any]:
    """Call one tool on a registered lane's MCP server.

    Spawns the lane's MCP server, calls the named tool, and returns the parsed
    JSON result. If the lane is down, slow, or unknown, returns an honest error
    dict.

    When governance_tier is set, checks the tier against a per-lane minimum.
    A T1-classified system cannot call tools that require T2+ authority.
    """
    args = args or {}

    # Governance gate: check if the lane requires a minimum tier
    if governance_tier:
        min_tier = LANE_MIN_TIERS.get(lane_name, "T1")
        if not _tier_allows(governance_tier, min_tier):
            return {
                "error": f"governance gate: lane {lane_name!r} requires tier "
                         f">= {min_tier}, but governance tier is {governance_tier}",
                "governance_denied": True,
            }

    from harness.lanes import resolve_mcp_command, LANES
    if lane_name not in LANES:
        return {"error": f"unknown lane: {lane_name!r}. "
                         f"Available: {sorted(LANES.keys())}"}

    try:
        command = resolve_mcp_command(lane_name)
    except Exception as e:
        return {"error": f"cannot resolve MCP command for {lane_name!r}: {e}"}

    try:
        from harness.mcp_client import MCPClient, MCPError
        with MCPClient(command, timeout=timeout,
                       client_name=f"flywheel-{lane_name}-proxy") as c:
            c.start()
            res = c.call_text(tool_name, args)
            if not res["ok"]:
                return {"error": f"{lane_name}.{tool_name} error: "
                                 f"{res['text'][:200]}"}
            try:
                return json.loads(res["text"])
            except json.JSONDecodeError:
                return {"raw": res["text"][:500]}
    except Exception as e:
        return {"error": f"lane {lane_name!r} unavailable: {type(e).__name__}: {e}"}


# Minimum TADR tier required to call each lane.
# Most lanes are T1 (open access). Lanes that can make real-world changes
# or access sensitive infrastructure require T2+. The kill switch requires T3.
LANE_MIN_TIERS: dict[str, str] = {
    "gather": "T1",
    "crucible": "T1",
    "index": "T1",
    "forum": "T1",
    "learn": "T1",
    "telos": "T1",
    "local-model": "T2",  # the propose-verify engine; can execute code
}


def _tier_allows(governance_tier: str, required_tier: str) -> bool:
    """Check whether the governance tier permits calling a lane."""
    ranks = {"T1": 1, "T2": 2, "T3": 3}
    return ranks.get(governance_tier, 0) >= ranks.get(required_tier, 1)


def list_available_lanes() -> list[dict[str, str]]:
    """Return the list of lanes with their minimum tier requirements."""
    from harness.lanes import LANES
    return [
        {
            "name": name,
            "min_tier": LANE_MIN_TIERS.get(name, "T1"),
            "description": getattr(lane, "description", ""),
            "organ": getattr(lane, "organ", ""),
        }
        for name, lane in LANES.items()
    ]
