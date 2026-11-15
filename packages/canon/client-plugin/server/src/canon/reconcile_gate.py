"""reconcile_gate.py -- V4: the pure gate/deadline kernel of the reconcile loop.

When a byte-drift rides on a persona whose basis is no longer sound, the reconcile
loop cannot fast-forward: the surface's state is under question and a human must
adjudicate. That adjudication is a gate, and the gate carries a durable deadline
so a stalled decision cannot hold a build hostage forever, yet a lapsed gate never
silently ships a change no one approved.

This module is the pure heart of that contract, split out so it proves in
isolation with no IO, no clock, and no pool. Two functions:

- resolve_with_deadline folds a frozen absolute deadline against an injected
  `now` into a final resolution. It reads no wall clock: the caller supplies the
  time, so the semantics are the caller's and the kernel stays deterministic.
- reconcile_action maps a resolution to the one bit the commit phase needs: write
  the approved render, or hold.

The resolution vocabulary and the on-expiry decisions mirror forum's gate model
(forum/src/forum/gates.py). canon owns its own copies because it imports no
engine, but the string values match forum's so the two cross-reference, and the
boundary matches forum's: now == deadline is not strictly-before, so it expires.
The default on_expiry is reject, forum's safe default: a gate no one answered
before its deadline lapses closed, never open.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable, Optional

# The gate resolution vocabulary, values identical to forum's (forum.gates).
APPROVED = "approved"
EDITED = "edited"
REJECTED = "rejected"
PENDING = "pending"

# The on-expiry decisions a lapsed gate folds to. reject is forum's safe default:
# a gate no one answered lapses closed. The map is the sole source of which
# on_expiry strings are legal, so the policy guard and the kernel agree.
ON_EXPIRY_APPROVE = "approve"
ON_EXPIRY_REJECT = "reject"
_EXPIRY_DECISIONS = {ON_EXPIRY_APPROVE: APPROVED, ON_EXPIRY_REJECT: REJECTED}

# The one bit the commit phase reads off a resolution.
ACTION_WRITE = "write"
ACTION_HOLD = "hold"

# The injected gate seams. gate_read looks up an already-raised gate for a
# surface (None when none is raised yet), read in the pure classify phase.
# gate_raise stages a new gate, called only in the commit phase. run_witness
# records the whole reconcile run once, after the commit.
GateRead = Callable[[Mapping], Optional[Mapping]]
GateRaise = Callable[[Mapping], None]
RunWitness = Callable[[Mapping], object]


@dataclass(frozen=True, slots=True)
class ConflictGatePolicy:
    """How a conflict gate lapses. deadline_seconds is the window from raise to
    expiry (None is unbounded: the gate waits for a human indefinitely). on_expiry
    is what a lapse decides, one of the _EXPIRY_DECISIONS keys. Refuses a
    non-positive deadline or an unknown on_expiry at construction, so a malformed
    policy is a loud fault at the edge, never a silent mis-gate later."""

    deadline_seconds: float | None = None
    on_expiry: str = ON_EXPIRY_REJECT

    def __post_init__(self) -> None:
        if self.deadline_seconds is not None and self.deadline_seconds <= 0:
            raise ValueError(
                f"deadline_seconds must be positive or None, "
                f"got {self.deadline_seconds!r}")
        if self.on_expiry not in _EXPIRY_DECISIONS:
            raise ValueError(
                f"on_expiry must be one of {sorted(_EXPIRY_DECISIONS)}, "
                f"got {self.on_expiry!r}")


def resolve_with_deadline(resolution: str, *, deadline: float | None,
                          now: float,
                          on_expiry: str = ON_EXPIRY_REJECT) -> str:
    """Fold a frozen deadline against `now` into a final resolution.

    A decided gate (anything but pending) passes through: an operator's decision
    is final and never re-evaluated against the clock. A pending gate with no
    deadline stays pending. A pending gate whose deadline has arrived lapses to
    the on_expiry decision; the boundary is forum's, so now == deadline expires
    (it is not strictly before the deadline). A garbage on_expiry can only reach
    here past the policy guard, and the kernel still fails closed to reject.
    """
    if resolution != PENDING:
        return resolution
    if deadline is None:
        return PENDING
    if float(now) < float(deadline):
        return PENDING
    return _EXPIRY_DECISIONS.get(on_expiry, REJECTED)


def reconcile_action(resolution: str) -> str:
    """Map a resolution to the commit bit: only an approval writes; edited,
    rejected, and pending all hold. A resolution outside the vocabulary is a
    wiring fault the caller must see, not a silent hold."""
    if resolution not in (APPROVED, EDITED, REJECTED, PENDING):
        raise ValueError(
            f"gate returned an out-of-vocabulary resolution: {resolution!r}")
    return ACTION_WRITE if resolution == APPROVED else ACTION_HOLD
