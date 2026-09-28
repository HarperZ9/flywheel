"""Which lane tools the engine admits, at which tier, and why.

One table: lane -> tool -> ``ToolPolicy``, for all 17 registry lanes. It is
the source for:

- the frozen build's admission: the payload generator writes each bundled
  lane's ``allowed_tools`` from ``admitted_tools`` (T1 and in the build), and the
  Node, local-model and writing launches carry the same list;
- the tier every lane call needs (``lane_caller.required_tier``), computed by
  the engine whether or not the caller sends one;
- Plugins and agent runs, which reach a lane tool only when it is T1, in the
  build and free of argument guards (``lane_tier_gate``).

The T2 rule: a tool whose ``effect`` writes outside the lane's own folder,
spends a model call or provider key, publishes, actuates or decides a human
approval is T2. ``validate_policy`` enforces it. A tool may sit at T2 for a
reviewed reason even when its effect alone would allow T1; the review document
marks those. Argument guards keep a T1 tool inside the rule: ``allowed_args``
passes only listed argument names (an allowlist, so a lane release that adds a
widening argument is dropped), ``forced_args`` then forces or drops named ones,
``id_args`` must be plain ids and ``path_args`` may not reach into the Flywheel
home outside the lane folder (``argument_refusal``).

The content lives in three data files split by lane family, plus the argument
facts in ``lane_tool_policy_args``. The decision of record is O-4
(``POLICY-DECISION.md``, rendered with the tables into
``project-docs/lanes/POLICY-REVIEW.md`` by ``scripts/render_lane_policy_review.py``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .lane_tool_policy_agents import AGENT_LANE_POLICY
from .lane_tool_policy_args import ARG_POLICY
from .lane_tool_policy_evidence import EVIDENCE_LANE_POLICY
from .lane_tool_policy_node import NODE_LANE_POLICY

TIERS = ("T1", "T2")
DEFAULT_TIMEOUT_S = 20
EFFECTS = {
    "read": "reads files or lane state and returns a result",
    "network_read": "fetches from the network and writes nothing",
    "state_write": "writes only inside the lane's own state folder",
    "model_call": "calls the model server the person set up; a provider key "
                  "reaches it only through a per-call grant",
    "outside_write": "writes or deletes outside the lane's own folder",
    "spend": "spends a model call or provider key",
    "publish": "publishes under an identity on a shared host",
    "actuate": "acts on the device or desktop",
    "approve": "decides a human approval gate",
}
T2_EFFECTS = frozenset(("outside_write", "spend", "publish", "actuate", "approve"))
SETUP_ITEMS = {
    "node": "Node.js 20 or later (bundled in the installer)",
    "git": "Git for Windows, for branch and history",
    "model_server": "a model server at one of the two fixed local addresses",
    "project_folder": "a project folder outside the Flywheel home",
    "canon_blocks": "authored blocks in <home>/lanes/canon/blocks",
    "provider_key": "a provider key granted to the lane and bound per call",
    "claude_cli": "a signed-in claude CLI the engine can find",
    "bulletin_identity": "a registered bulletin identity",
    "writing_draft": "a draft revision recorded on the Writing screen",
}
#: Lanes whose main action is a T2 tool: the card says the call needs a T2
#: approval. writing's diagnose writes into the engine's journey store (C-5).
GRANTED_MAIN_LANES = frozenset(("writing",))
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
#: Windows opens these names as devices whatever the extension, so a lane that
#: joins an id into ``<id>.json`` must never receive one (any letter case).
WINDOWS_DEVICE_STEMS = frozenset(
    ("CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)),
     *(f"LPT{n}" for n in range(1, 10))))
READS_ONLY_LANES = {
    "calibrate-pro": "Reads the panel catalog. Calibration runs in Calibrate Pro itself.",
}
#: Lanes held out of this build, with the card's sentence. A held lane admits no
#: tool and has no main tool; the frozen engine reports ``lane_held`` for it.
#: None is held: telos was, until 0.4.2 removed the release contents under review
#: and its tools were classified one by one (lane_tool_policy_node). The
#: mechanism stays for a lane that needs it again.
HELD_LANES: dict[str, str] = {}


@dataclass(frozen=True)
class ToolPolicy:
    """How one lane tool is admitted.

    ``tier``: T1 runs on an ordinary lane call; T2 needs a granted operation.
    ``timeout_s``: the call timeout the engine applies (draft values, unmeasured).
    ``needs``: setup item ids (``SETUP_ITEMS``) that must be met first.
    ``main``: the tool is one of the lane's main actions.
    ``not_in_build``: a reason slug when this build cannot run the tool.
    ``effect``: what the tool does, from ``EFFECTS``; drives the T2 rule.
    ``reason``: one sentence for the reviewer, from reading the lane source.
    ``forced_args``: (name, value) pairs the engine applies to every call on
    every route, after ``allowed_args``; ``None`` drops the argument.
    ``allowed_args``: when a tuple, the only argument names that pass.
    ``id_args``, ``path_args``, ``tree_args``, ``tree_base``, ``open_egress``,
    ``launch_grant``: see ``lane_tool_policy_args``.
    """
    tier: str = "T1"
    timeout_s: int = DEFAULT_TIMEOUT_S
    needs: tuple[str, ...] = ()
    main: bool = False
    not_in_build: str = ""
    effect: str = "read"
    reason: str = ""
    forced_args: tuple[tuple[str, Any], ...] = ()
    allowed_args: tuple[str, ...] | None = None
    id_args: tuple[str, ...] = ()
    path_args: tuple[str, ...] = ()
    tree_args: tuple[str, ...] = ()
    tree_base: str = ""
    open_egress: bool = False
    launch_grant: str = ""

    @property
    def guarded(self) -> bool:
        """True when the engine rewrites or checks this tool's arguments."""
        return bool(self.forced_args or self.allowed_args is not None
                    or self.id_args or self.path_args or self.tree_args)


def _build(tables: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, dict[str, ToolPolicy]]:
    return {lane: {name: ToolPolicy(**fields, **ARG_POLICY.get(lane, {}).get(name, {}))
                   for name, fields in tools.items()}
            for lane, tools in tables.items()}


LANE_TOOL_POLICY: dict[str, dict[str, ToolPolicy]] = {
    **_build(EVIDENCE_LANE_POLICY), **_build(AGENT_LANE_POLICY), **_build(NODE_LANE_POLICY)}


def lane_policy(lane: str) -> dict[str, ToolPolicy]:
    """The tool table for one lane; empty when the lane has none."""
    return dict(LANE_TOOL_POLICY.get(lane, {}))


def tool_policy(lane: str, tool: str) -> ToolPolicy | None:
    """One tool's entry, or None when the table does not list it."""
    return LANE_TOOL_POLICY.get(lane, {}).get(tool)


def admitted_tools(lane: str) -> list[str]:
    """The tools a lane launch admits: T1 and in this build, in table order."""
    return [name for name, entry in LANE_TOOL_POLICY.get(lane, {}).items()
            if entry.tier == "T1" and not entry.not_in_build]


def main_tools(lane: str) -> list[str]:
    """The lane's main-action tools, in table order."""
    return [name for name, entry in LANE_TOOL_POLICY.get(lane, {}).items() if entry.main]


def guard_args(lane: str, tool: str, args: Mapping[str, Any]) -> dict[str, Any]:
    """``args`` filtered to ``allowed_args``, then with the forced arguments
    applied; the input is not changed."""
    entry = tool_policy(lane, tool)
    allowed = entry.allowed_args if entry else None
    out = {k: v for k, v in args.items() if allowed is None or k in allowed}
    for name, value in (entry.forced_args if entry else ()):
        if value is None:
            out.pop(name, None)
        else:
            out[name] = value
    return out


def _entry_problems(where: str, entry: ToolPolicy, granted_main: bool = False,
                    lane: str = "") -> list[str]:
    problems: list[str] = []
    if entry.tier not in TIERS:
        problems.append(f"{where}: tier {entry.tier!r} not in {TIERS}")
    if not isinstance(entry.timeout_s, int) or entry.timeout_s <= 0:
        problems.append(f"{where}: timeout_s must be a positive int")
    for item in entry.needs:
        if item not in SETUP_ITEMS:
            problems.append(f"{where}: unknown setup item {item!r}")
    if entry.main and (entry.not_in_build or (entry.tier != "T1" and not granted_main)):
        problems.append(f"{where}: a main tool must be T1 and in the build")
    if entry.effect not in EFFECTS:
        problems.append(f"{where}: effect {entry.effect!r} not in EFFECTS")
    elif entry.effect in T2_EFFECTS and entry.tier != "T2":
        problems.append(f"{where}: effect {entry.effect!r} needs T2")
    if not (isinstance(entry.reason, str) and entry.reason.strip()):
        problems.append(f"{where}: no reason")
    if any(not (isinstance(pair, tuple) and len(pair) == 2 and isinstance(pair[0], str))
           for pair in entry.forced_args):
        problems.append(f"{where}: forced_args must be (name, value) pairs")
    if entry.tree_base and (entry.tree_base not in entry.path_args or not entry.tree_args):
        problems.append(f"{where}: a tree base must be a path argument of a tool with a "
                        "tree argument")
    if entry.launch_grant:
        from .lane_tool_policy_args import LAUNCH_GRANTS
        if entry.launch_grant not in LAUNCH_GRANTS.get(lane, {}):
            problems.append(f"{where}: launch grant {entry.launch_grant!r} is not one "
                            "the lane takes")
        if entry.tier != "T2" or entry.not_in_build:
            problems.append(f"{where}: a launch grant needs a T2 tool in the build")
    return problems


def validate_policy(
    table: dict[str, dict[str, ToolPolicy]] | None = None,
) -> list[str]:
    """Every schema or rule defect in the table, as short messages; empty when sound."""
    problems: list[str] = []
    for lane, tools in (LANE_TOOL_POLICY if table is None else table).items():
        if not tools:
            problems.append(f"{lane}: no tools")
        for name, entry in tools.items():
            where = name if name.startswith(f"{lane}.") else f"{lane} {name}"
            if not isinstance(entry, ToolPolicy):
                problems.append(f"{where}: not a ToolPolicy")
                continue
            problems.extend(_entry_problems(where, entry, lane in GRANTED_MAIN_LANES,
                                            lane))
    return problems
