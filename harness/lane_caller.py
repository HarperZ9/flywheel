"""lane_caller.py -- generic MCP lane caller for the gateway.

Generalizes _forum_mcp_call: spawns any registered lane's MCP server, calls
the named tool, and returns the parsed JSON. Gated by tier: the engine computes
the tier each call needs from the lane tool policy, whether or not the caller
sends one, and a call that sends none runs at T1.

The key rule (POLICY-DECISION C-8): a call whose child would receive a
provider key needs T2. A bound credential makes the call T2; below T2 the
child's key-shaped ``env_allow`` names are stripped, so a T1 call never spends
a key. Argument guards run before any child spawns (``lane_tier_gate``).

A tool whose work outlives the call (a relay background run, an index router
job) goes to the lane's long-lived session instead of a per-call child
(``lane_session``), after the same checks.
"""
from __future__ import annotations

import json
from typing import Any

from .lane_tool_policy import LANE_TOOL_POLICY, tool_policy


def call_lane_tool(
    lane_name: str,
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    timeout: int = 20,
    governance_tier: str = "",
    bulletin_access: object = None,
    credential_bindings: object = None,
) -> dict[str, Any]:
    """Call one tool on a registered lane's MCP server.

    Spawns the lane's MCP server, calls the named tool, and returns the parsed
    JSON result. If the lane is down, slow, or unknown, returns an honest error
    dict. A call runs at ``governance_tier`` or, when none is sent, at T1; the
    tier it needs comes from ``required_tier``. A granted T2 call widens a
    restricted launch for its one tool (lane_tier_gate). credential_bindings
    carries the values a grant bound for this call; they join this child only.
    """
    from .lanes_registry import LANES
    if lane_name not in LANES:   # before the tier: an unknown lane is not a denial
        return _unknown_lane(lane_name)
    tier = governance_tier or "T1"
    min_tier = required_tier(lane_name, tool_name)
    from .lane_credentials import binds_any_key
    if binds_any_key(credential_bindings) and _RANKS.get(min_tier, 1) < 2:
        min_tier = "T2"   # the key rule: a call that would spend a key is T2
    if not _tier_allows(tier, min_tier):
        return {"error": f"governance gate: {lane_name}.{tool_name} requires tier "
                         f">= {min_tier}, but governance tier is "
                         f"{governance_tier or 'T1 (none sent)'}",
                "governance_denied": True}
    from .bulletin_access import bulletin_access_denial
    denial = bulletin_access_denial(
        lane_name, tool_name, requested_access=bulletin_access)
    if denial is not None:
        return denial
    from .lane_tier_gate import argument_refusal, guard_args
    refused = argument_refusal(lane_name, tool_name, args or {})
    if refused is not None:
        return refused
    command = _launch_for_call(lane_name, tool_name, tier, credential_bindings)
    if isinstance(command, dict):
        return command
    args = guard_args(lane_name, tool_name, args or {})
    from .lane_session import is_session_tool
    if is_session_tool(lane_name, tool_name):   # the work outlives the call (WP10)
        from .lane_session_calls import session_call
        return session_call(lane_name, tool_name, command, args, timeout, credential_bindings)
    return _call(lane_name, tool_name, command, args, timeout)


def _launch_for_call(lane_name: str, tool_name: str, tier: str,
                     credential_bindings: object) -> Any:
    """The launch for this one call, or the refusal dict to return."""
    from harness.lanes import resolve_mcp_launch, LANES
    if lane_name not in LANES:
        return _unknown_lane(lane_name)
    try:
        command = resolve_mcp_launch(lane_name)
    except Exception as e:
        return {"error": f"cannot resolve MCP command for {lane_name!r}: {e}"}
    from .lane_credentials import (LaneCredentialError, bind_lane_credentials,
                                   credential_refused, strip_key_grants)
    if not _tier_allows(tier, "T2"):
        command = strip_key_grants(lane_name, command)   # the key rule, C-8
    try:  # a saved key granted to this lane joins this one child (lane_credentials.py)
        command = bind_lane_credentials(lane_name, command, credential_bindings)
    except LaneCredentialError:
        return credential_refused(lane_name, tool_name)
    from .lane_tier_gate import admission_refusal, widen_for_call
    command = widen_for_call(command, lane_name, tool_name, tier)
    return admission_refusal(command, lane_name, tool_name) or command


def _unknown_lane(lane_name: str) -> dict[str, Any]:
    from .lanes_registry import LANES
    return {"error": f"unknown lane: {lane_name!r}. Available: {sorted(LANES.keys())}"}


def _call(lane_name: str, tool_name: str, command: Any, args: dict[str, Any],
          timeout: int) -> dict[str, Any]:
    """Start the child, call the tool once. A failure to start reads "lane ...
    unavailable"; a failure once the child answered initialize reads "lane ...
    call failed", so a tool that crashes its server mid-call is not reported as
    a lane that cannot launch (C8)."""
    started = False
    try:
        from harness.mcp_client import MCPClient
        with MCPClient(command, timeout=timeout,
                       client_name=f"flywheel-{lane_name}-proxy") as c:
            started = True
            res = c.call_text(tool_name, args)
            if not res["ok"]:
                return {"error": f"{lane_name}.{tool_name} error: "
                                 f"{res['text'][:200]}"}
            try:
                return json.loads(res["text"])
            except json.JSONDecodeError:
                return {"raw": res["text"][:500]}
    except Exception as e:
        stage = "call failed" if started else "unavailable"
        return {"error": f"lane {lane_name!r} {stage}: {type(e).__name__}: {e}"}


# Lane floors: the headline tier the lane listing shows for each lane. Most
# lanes are T1. Lanes that can make real-world changes or reach sensitive
# infrastructure show T2. A floor no longer decides any call: a listed tool takes
# the tier the table gives it, and an unlisted tool takes UNLISTED_TOOL_TIER. The
# floor stays as the bar a table entry must be reviewed to go below
# (tests/test_lane_caller.py REVIEWED_BELOW_FLOOR).
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

# Default deny (O-12, DECISIONS.json): a tool the policy table does not list is
# T2 on every lane and in every install mode. On a pip or source install such a
# tool is one a newer lane release added, and a server's tool definitions are
# untrusted until reviewed, so it runs only on a call the owner approved at T2.
# A frozen build admits listed tools only, so there it is refused even at T2.
# Plugins and agent runs refuse it outright (lane_tier_gate, C-11). The cost is
# that a new read tool needs a T2 approval until the table lists it, which is
# the safe direction: a gate that widens on its own when a lane grows is not a
# gate.
UNLISTED_TOOL_TIER = "T2"

TOOL_MIN_TIERS: dict[str, dict[str, str]] = {
    lane: {name: entry.tier for name, entry in tools.items()}
    for lane, tools in LANE_TOOL_POLICY.items()
}

_RANKS = {"T1": 1, "T2": 2, "T3": 3}


def required_tier(lane_name: str, tool_name: str) -> str:
    """The tier one call needs: the table's entry, else T2 (O-12)."""
    entry = tool_policy(lane_name, tool_name)
    return entry.tier if entry is not None else UNLISTED_TOOL_TIER


def _tier_allows(governance_tier: str, required: str) -> bool:
    """Check whether the governance tier permits the call."""
    return _RANKS.get(governance_tier, 0) >= _RANKS.get(required, 1)


def list_available_lanes() -> list[dict[str, object]]:
    """Return the list of lanes with their minimum tier requirements.

    Each lane carries its tool tiers from the policy table and the tier an
    unlisted tool costs, so a client reading the floor alone cannot conclude
    that every tool on that lane shares it.
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
        entry["unlisted_tool_tier"] = UNLISTED_TOOL_TIER
        if name == "bulletin":
            from .bulletin_access import policy_summary
            entry["bulletin_access_policy"] = policy_summary()
        listing.append(entry)
    return listing
