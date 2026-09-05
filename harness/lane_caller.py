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

    When governance_tier is set, checks the tier against the lane's floor,
    raised by the tool's own entry. A T1-classified system cannot call tools
    that require T2+ authority.
    """
    args = args or {}

    # Governance gate: the tier this lane and tool together require
    if governance_tier:
        min_tier = required_tier(lane_name, tool_name)
        if not _tier_allows(governance_tier, min_tier):
            return {
                "error": f"governance gate: {lane_name}.{tool_name} requires tier "
                         f">= {min_tier}, but governance tier is {governance_tier}",
                "governance_denied": True,
            }

    from harness.lanes import resolve_mcp_launch, LANES
    if lane_name not in LANES:
        return {"error": f"unknown lane: {lane_name!r}. "
                         f"Available: {sorted(LANES.keys())}"}

    try:
        command = resolve_mcp_launch(lane_name)
    except Exception as e:
        return {"error": f"cannot resolve MCP command for {lane_name!r}: {e}"}

    try:
        from harness.mcp_client import MCPClient, MCPError
        with MCPClient(command, timeout=timeout,
                       client_name=f"flywheel-{lane_name}-proxy") as c:
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
    "accountable-surface": "T2",  # actuates via effectors (fs/command/web/browser)
    "relay": "T2",  # the execution lane: a gated agent loop that runs code (run/exec)
}

# The lane floor cannot say that reading a public board and posting to it are
# different acts. bulletin is the live case: reading is what the board is for,
# and writing publishes under a persistent identity on a host other people read.
# So a lane may carry a per-tool map, and the tier a call needs is the lane
# floor raised by the tool's own entry.
#
# An unlisted tool on a mapped lane takes SPLIT_DEFAULT_TIER, never the floor.
# A write tool added to the board later would otherwise arrive open at T1, and a
# gate that widens on its own when the far side grows is not a gate. The cost is
# that a new read tool is refused until it is listed here, which is the safe
# direction and which the error names.
SPLIT_DEFAULT_TIER = "T2"

TOOL_MIN_TIERS: dict[str, dict[str, str]] = {
    "bulletin": {
        # health, and the board's own read surface (its src/tools/read.ts)
        "bulletin_status": "T1",
        "bulletin_doctor": "T1",
        "board_rooms": "T1",
        "board_feed": "T1",
        "board_search": "T1",
        "board_thread": "T1",
        "board_post": "T1",
        "board_agents": "T1",
        "board_agent": "T1",
        "board_digest": "T1",
        "board_stats": "T1",
        "board_moderation_log": "T1",
        # signed, but they answer about the caller's own key and change nothing
        "board_whoami": "T1",
        "board_inbox": "T1",
    },
}

_RANKS = {"T1": 1, "T2": 2, "T3": 3}


def required_tier(lane_name: str, tool_name: str) -> str:
    """The tier one call needs: the lane floor, raised by the tool's entry."""
    floor = LANE_MIN_TIERS.get(lane_name, "T1")
    per_tool = TOOL_MIN_TIERS.get(lane_name)
    if per_tool is None:
        return floor
    tool = per_tool.get(tool_name, SPLIT_DEFAULT_TIER)
    return tool if _RANKS.get(tool, 3) > _RANKS.get(floor, 1) else floor


def _tier_allows(governance_tier: str, required: str) -> bool:
    """Check whether the governance tier permits the call."""
    return _RANKS.get(governance_tier, 0) >= _RANKS.get(required, 1)


def list_available_lanes() -> list[dict[str, object]]:
    """Return the list of lanes with their minimum tier requirements.

    A lane whose tools do not share one tier carries the open set and the tier
    everything else needs, so a client reading the floor alone cannot conclude
    that every tool on that lane is open.
    """
    from harness.lanes import LANES
    listing: list[dict[str, object]] = []
    for name, lane in LANES.items():
        entry: dict[str, object] = {
            "name": name,
            "min_tier": LANE_MIN_TIERS.get(name, "T1"),
            "description": getattr(lane, "role", ""),
            "organ": getattr(lane, "organ", ""),
        }
        per_tool = TOOL_MIN_TIERS.get(name)
        if per_tool:
            entry["tool_tiers"] = dict(per_tool)
            entry["unlisted_tool_tier"] = SPLIT_DEFAULT_TIER
        listing.append(entry)
    return listing
