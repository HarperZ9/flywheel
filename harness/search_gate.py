"""search_gate.py -- an adaptive-effort gate in front of best-of-N search.

Search draws K candidates and the visible suite picks the first one that
passes, in proposal order. Any candidate drawn after that first pass can never
change the pick, so drawing it spends a sample for nothing. The gate stops the
draw early:

  off         draw all K (the default; today's behaviour)
  first-pass  draw the temperature-0 candidate; stop if it passes the visible
              suite, otherwise draw the remaining K - 1
  sequential  stop at the first candidate that passes the visible suite

The decider (held-out suite) still runs once on the pick, so the gate cannot
add an accept the decider rejects. With a deterministic proposer the pick is
the same as full search; the replay functions below let a reader check that on
logged candidates instead of trusting it.
"""
from __future__ import annotations

from typing import Sequence

GATES = ("off", "first-pass", "sequential")


def check_gate(gate: str) -> str:
    if gate not in GATES:
        raise ValueError(f"unknown effort gate {gate!r}; expected one of {GATES}")
    return gate


def should_stop(gate: str, index: int, passed: bool) -> bool:
    """True when the gate ends the draw after candidate `index`."""
    if gate == "first-pass":
        return index == 0 and passed
    if gate == "sequential":
        return passed
    return False


def gated_draws(gate: str, passes: Sequence[bool]) -> int:
    """Candidates the gate draws, given the visible verdict of each of the K."""
    check_gate(gate)
    for i, ok in enumerate(passes):
        if should_stop(gate, i, ok):
            return i + 1
    return len(passes)


def gated_pick(gate: str, passes: Sequence[bool]) -> int | None:
    """Index of the candidate search would select among the drawn ones."""
    drawn = passes[:gated_draws(gate, passes)]
    return next((i for i, ok in enumerate(drawn) if ok), None)


def replay_logged(gate: str, visible: Sequence[bool], held: Sequence[bool]) -> dict:
    """Exact replay on a fully logged candidate list (visible and held-out verdicts)."""
    pick = gated_pick(gate, visible)
    return {"draws": gated_draws(gate, visible), "pick": pick,
            "held": bool(pick is not None and held[pick])}


def replay_record(gate: str, row: dict, k: int = 4) -> dict:
    """Replay on a G4 held-out rerun row, which logs only the first sample and the result.

    Assumes the single arm's temperature-0 attempt is search's first candidate.
    The sequential gate cannot be replayed: candidate positions were not logged.
    """
    if gate == "sequential":
        raise ValueError("G4 records do not log candidate positions; replay first-pass")
    check_gate(gate)
    if gate == "first-pass" and row["single_visible"]:
        return {"draws": 1, "held": bool(row["single_held"]),
                "consistent": bool(row["self_scored_accept"])}
    return {"draws": k, "held": bool(row["search_held"]), "consistent": True}
