"""workstream_audit.py -- the part of a stack a person still has to read.

A verified goal over thirty thousand lemmas is worth nothing if the top
statement does not say what the paper says. No kernel decides that. What the
machinery can do is bound the reading: name the small set of statements a person
has to look at, say why each one is on the list, and pin each reading to the
exact text that was read so a later edit un-reads it.

Membership is structural, so nobody picks what gets audited:

  the goal              the boundary with the informal claim the stack is for
  a direct dependency   the lemmas that structure that claim
  an assumption         nothing checked it, so a person asserted it

Everything else is delegated, and the reason is not laziness. Faithfulness is a
question at the boundary between a formal statement and an informal one. An
intermediate lemma that a kernel accepted, and that a kernel-accepted proof uses,
carries the goal whether or not its wording reads well to a person. Reuse does
not change that, so a lemma many others rest on is delegated too, which is what
keeps the surface from growing as a shared corpus grows.

The bound is a property, not a hope: the surface holds the goal, the goal's own
dependencies, and the assumptions. Adding an obligation that is none of those
leaves it exactly as it was. tests/test_workstream_audit.py asserts that over
generated graphs.

A recorded reading pins the statement, its check kind, and its environment, and
deliberately not the subtree beneath it. The workstream digest folds in
dependencies so a swapped lemma moves the goal's identity. That is right for a
verdict and wrong for a reading, because a proof rewritten three levels down does
not change what a milestone statement says. Pinning the folded digest would
expire every human reading on every proof edit, and an audit nobody can keep
current is an audit nobody does.
"""
from __future__ import annotations

from harness.evidence_json import canonical_sha256, strict_load_json
from harness.workstream import Obligation, Workstream, WorkstreamError

AUDIT_SCHEMA = "flywheel.workstream.audit/v1"

AUDITED = "audited"
STALE = "stale"
UNAUDITED = "unaudited"

_GOAL = "the goal statement"
_STRUCTURE = "a direct dependency of the goal, so it structures the claim"
_CARRIED = "carried, not checked"

_MAX_DOCUMENT = 32_000_000


def statement_digest(obligation: Obligation) -> str:
    """What a reading pins: the text, the kind of check, and the environment.

    Not workstream.digests, which folds in the subtree. See the module docstring
    for why a reading has to survive a proof edit underneath it.
    """
    return canonical_sha256({
        "statement": obligation.statement,
        "check": obligation.check,
        "environment": obligation.environment,
    })


def _reasons(workstream: Workstream, reached: tuple[str, ...]) -> dict[str, list[str]]:
    """Why each obligation on the surface is there. Structural, never chosen."""
    structure = set(workstream.nodes[workstream.goal].depends_on)
    surface: dict[str, list[str]] = {}
    for node_id in reached:
        node = workstream.nodes[node_id]
        why = []
        if node_id == workstream.goal:
            why.append(_GOAL)
        if node_id in structure:
            why.append(_STRUCTURE)
        if node.check == "assumed":
            why.append(_CARRIED)
        if why:
            surface[node_id] = why
    return surface


def _caveat(counts: dict[str, int], stale: list[str], unaudited: list[str]) -> list[str]:
    """Derived from what the surface holds. Never written by a caller."""
    lines = [
        "a recorded reading says a person read the statement; it does not say the "
        "reading was right, and nothing here compares a statement to its source",
        "a reading pins the statement, its check kind, and its environment, and "
        "says nothing about the obligations beneath it",
    ]
    if counts["delegated"]:
        lines.append(
            f"{counts['delegated']} of {counts['reached']} obligations under the goal "
            "are delegated and were never on the surface")
    if stale:
        lines.append(
            f"{len(stale)} statement(s) changed after they were read, so the earlier "
            f"reading is not carried forward: {', '.join(stale)}")
    if unaudited:
        lines.append(f"{len(unaudited)} statement(s) on the surface have no recorded reading")
    return lines


def audit_surface(workstream: Workstream,
                  audited: dict[str, str] | None = None) -> dict:
    """The bounded reading a person owes this stack, and what is already read."""
    recorded = dict(audited or {})
    unknown = sorted(set(recorded) - set(workstream.nodes))
    if unknown:
        raise WorkstreamError(f"{unknown[0]} carries a reading but is not an obligation")
    reached = workstream.reachable()
    reasons = _reasons(workstream, reached)
    entries: dict[str, dict] = {}
    stale: list[str] = []
    unread: list[str] = []
    for node_id in sorted(reasons):
        node = workstream.nodes[node_id]
        pin = statement_digest(node)
        signed = recorded.get(node_id)
        if signed is None:
            state = UNAUDITED
            unread.append(node_id)
        elif signed == pin:
            state = AUDITED
        else:
            state = STALE
            stale.append(node_id)
        entries[node_id] = {
            "reasons": reasons[node_id],
            "statement": node.statement,
            "check": node.check,
            "environment": node.environment,
            "statement_digest": pin,
            "state": state,
        }
    counts = {
        "reached": len(reached),
        "surface": len(entries),
        "delegated": len(reached) - len(entries),
        "audited": sum(1 for row in entries.values() if row["state"] == AUDITED),
        "stale": len(stale),
        "unaudited": len(unread),
    }
    return {
        "schema": AUDIT_SCHEMA,
        "workstream_id": workstream.workstream_id,
        "goal": workstream.goal,
        "surface": entries,
        "counts": counts,
        "stale": stale,
        "unaudited": unread,
        "does_not_prove": _caveat(counts, stale, unread),
    }


def recorded_audits(document: str) -> dict[str, str]:
    """Readings carried inside a declaration, as `"audited": "<digest>"`.

    Read here rather than in load_workstream because a reading is not part of
    the workstream. It is a record about one, and a declaration that carries no
    readings is a complete declaration.
    """
    body = strict_load_json(document, max_bytes=_MAX_DOCUMENT)
    listed = body.get("obligations")
    if not isinstance(listed, list):
        raise WorkstreamError("a declaration carries a goal string and an obligations list")
    readings: dict[str, str] = {}
    for entry in listed:
        if not isinstance(entry, dict):
            raise WorkstreamError("every obligation is an object")
        signed = entry.get("audited")
        if signed is None:
            continue
        if not isinstance(signed, str) or len(signed) != 64:
            raise WorkstreamError("audited is the 64-character statement digest that was read")
        readings[entry.get("id", "")] = signed
    return readings
