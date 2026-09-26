"""Which lane tools the frozen build admits, at which tier, and why.

One table: lane -> tool -> ``ToolPolicy``. The payload generator derives each
bundled lane's ``allowed_tools`` from it (T1 tools that are in the build), and
the manifest check holds every row to it, so a row cannot admit a tool this
table does not.

This is the schema and a stub. The stub admits each Python payload lane's
status and doctor tools and nothing else, which is exactly what the 1.0.x rows
admit. The Node lanes (learn, telos) carry a full draft from
``lane_tool_policy_node.py``. Main tools, per-tool needs and T2 tools for the
other lanes, and the lanes without a payload (local-model, writing, bulletin),
arrive with the policy content. The operator reviews both before merge.
"""
from __future__ import annotations

from dataclasses import dataclass

from .lane_tool_policy_node import NODE_LANE_POLICY

TIERS = ("T1", "T2")
DEFAULT_TIMEOUT_S = 20


@dataclass(frozen=True)
class ToolPolicy:
    """How one lane tool is admitted.

    ``tier``: T1 runs on an ordinary lane call; T2 needs a granted operation.
    ``timeout_s``: the call timeout the engine applies.
    ``needs``: setup item ids that must be met before the tool can run.
    ``main``: the tool is one of the lane's main actions.
    ``not_in_build``: a reason slug when this build cannot run the tool; empty
    when it can.
    """
    tier: str = "T1"
    timeout_s: int = DEFAULT_TIMEOUT_S
    needs: tuple[str, ...] = ()
    main: bool = False
    not_in_build: str = ""


_HEALTH = ToolPolicy()


def _health_only(lane: str) -> dict[str, ToolPolicy]:
    return {f"{lane}.status": _HEALTH, f"{lane}.doctor": _HEALTH}


LANE_TOOL_POLICY: dict[str, dict[str, ToolPolicy]] = {
    lane: _health_only(lane)
    for lane in (
        "gather", "crucible", "index", "forum", "plexus", "mneme", "canon",
        "chorus", "relay", "accountable-surface", "articulate", "calibrate-pro",
    )
}
LANE_TOOL_POLICY.update({lane: {name: ToolPolicy(**fields) for name, fields in tools.items()}
                         for lane, tools in NODE_LANE_POLICY.items()})


def lane_policy(lane: str) -> dict[str, ToolPolicy]:
    """The tool table for one lane; empty when the lane has none yet."""
    return dict(LANE_TOOL_POLICY.get(lane, {}))


def admitted_tools(lane: str) -> list[str]:
    """The tools a lane launch admits: T1 and in this build, in table order."""
    return [name for name, policy in LANE_TOOL_POLICY.get(lane, {}).items()
            if policy.tier == "T1" and not policy.not_in_build]


def main_tools(lane: str) -> list[str]:
    """The lane's main-action tools, in table order."""
    return [name for name, policy in LANE_TOOL_POLICY.get(lane, {}).items() if policy.main]


def validate_policy(
    table: dict[str, dict[str, ToolPolicy]] | None = None,
) -> list[str]:
    """Every schema defect in the table, as short messages; empty when sound."""
    problems: list[str] = []
    for lane, tools in (LANE_TOOL_POLICY if table is None else table).items():
        if not tools:
            problems.append(f"{lane}: no tools")
        for name, policy in tools.items():
            where = f"{lane}.{name}" if not name.startswith(f"{lane}.") else name
            if not isinstance(policy, ToolPolicy):
                problems.append(f"{where}: not a ToolPolicy")
                continue
            if policy.tier not in TIERS:
                problems.append(f"{where}: tier {policy.tier!r} not in {TIERS}")
            if not isinstance(policy.timeout_s, int) or policy.timeout_s <= 0:
                problems.append(f"{where}: timeout_s must be a positive int")
            if not all(isinstance(item, str) and item for item in policy.needs):
                problems.append(f"{where}: needs must be non-empty strings")
            if policy.main and policy.not_in_build:
                problems.append(f"{where}: a main tool cannot be not_in_build")
    return problems
