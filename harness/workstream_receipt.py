"""workstream_receipt.py -- the workstream record a stranger re-derives.

The settled standings on their own are not a record. What makes them one is the
pair of footprints and the caveat: which environments the goal actually rests on,
which assumptions were carried rather than checked, and what a verified goal
still fails to establish.

does_not_prove is derived here from what settled, never supplied by a caller. A
record that reports only its proof is how a true explanation turns into a fake
passport, so the caveat is computed from the same data as the verdict and cannot
be edited without editing the standings that produced it.
"""
from __future__ import annotations

from harness.workstream import (
    BLOCKED, PENDING, REFUTED, SCHEMA, UNDECIDED, UNVERIFIABLE, VERIFIED,
    Workstream, settle,
)

# What a kind of check still fails to establish once it has passed. Keyed by
# kind rather than written per receipt, because the limit of a method does not
# change with the workstream it was used in, and a caveat a caller can phrase is
# a caveat a caller can soften. Counted over what actually settled by the
# method, never over what merely declared it: a caveat about a check that did
# not run reads as though it did.
_KIND_CAVEATS = {
    "readback": ("were settled by read-back; a confirmed read-back records that a "
                 "person compared a rendering against a source, not that the "
                 "renderer was independent of that source, and not that the "
                 "comparison was right"),
    "instrument": ("were checked against a driver reference file; that shows the "
                   "record is consistent with what the driver permits, not that "
                   "the device performed the run or that the reading is accurate"),
}


def _does_not_prove(settled: dict[str, dict], reached: tuple[str, ...],
                    assumptions: list[str], environments: list[str]) -> list[str]:
    """Derived from what settled. Never written by a caller, never empty."""
    lines = [
        "a verified standing records that each named check passed in its pinned "
        "environment; it does not establish that the statements say what a reader "
        "takes them to say",
    ]
    if assumptions:
        lines.append(
            f"the goal is conditional on {len(assumptions)} declared assumption(s), "
            f"carried and not checked: {', '.join(assumptions)}")
    kinds: dict[str, int] = {}
    counts: dict[str, int] = {}
    for node_id in reached:
        standing = settled[node_id]["standing"]
        counts[standing] = counts.get(standing, 0) + 1
        if standing == VERIFIED:
            kind = settled[node_id]["check"]
            kinds[kind] = kinds.get(kind, 0) + 1
    for kind in sorted(_KIND_CAVEATS):
        if kinds.get(kind):
            lines.append(f"{kinds[kind]} obligation(s) under the goal {_KIND_CAVEATS[kind]}")
    for standing in (PENDING, BLOCKED, UNDECIDED, UNVERIFIABLE, REFUTED):
        if counts.get(standing):
            lines.append(f"{counts[standing]} obligation(s) under the goal are {standing}")
    if len(environments) > 1:
        lines.append(
            f"obligations were settled across {len(environments)} environments; "
            "results are comparable only where the environment matches")
    return lines


def workstream_receipt(workstream: Workstream,
                       results: dict[str, object] | None = None) -> dict:
    """Standings, footprints, and the caveat, in one strict object."""
    settled = settle(workstream, results)
    reached = workstream.reachable()
    assumptions = sorted(
        node for node in reached if workstream.nodes[node].check == "assumed")
    environments = sorted({workstream.nodes[node].environment for node in reached})
    counts: dict[str, int] = {}
    for record in settled.values():
        counts[record["standing"]] = counts.get(record["standing"], 0) + 1
    return {
        "schema": SCHEMA,
        "workstream_id": workstream.workstream_id,
        "goal": workstream.goal,
        "goal_standing": settled[workstream.goal]["standing"],
        "goal_reason": settled[workstream.goal]["reason"],
        "obligations": {node_id: settled[node_id] for node_id in sorted(settled)},
        "counts": {name: counts[name] for name in sorted(counts)},
        "reached_from_goal": list(reached),
        "environment_footprint": environments,
        "assumption_footprint": assumptions,
        "does_not_prove": _does_not_prove(settled, reached, assumptions, environments),
    }
