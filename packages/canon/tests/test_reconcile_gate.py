"""test_reconcile_gate.py -- V4: the pure gate/deadline kernel.

The reconcile loop raises a human gate when a byte-drift rides on a persona whose
basis is no longer sound. That gate carries a durable deadline: it is frozen at
raise time and read back on a later resume, evaluated against an injected clock,
never a background timer. This kernel is the pure heart of that contract, so it
is proven in isolation before the orchestrator wires it.

The resolution vocabulary and the on-expiry decisions mirror forum's gate model
(forum/src/forum/gates.py), so a reader can cross-reference the two engines:
approved / edited / rejected / pending, and a lapsed gate defaults to reject so
it never silently ships. The boundary is forum's: now == deadline expires.
"""
from __future__ import annotations

from canon.reconcile_gate import (
    ACTION_HOLD,
    ACTION_WRITE,
    APPROVED,
    EDITED,
    ON_EXPIRY_APPROVE,
    ON_EXPIRY_REJECT,
    PENDING,
    REJECTED,
    ConflictGatePolicy,
    reconcile_action,
    resolve_with_deadline,
)


# -- the resolution vocabulary matches forum ------------------------------

def test_resolution_values_mirror_forum():
    # forum/src/forum/gates.py binds these exact strings; canon owns its own
    # copies (it imports no engine) but the values must not drift from forum.
    assert APPROVED == "approved"
    assert EDITED == "edited"
    assert REJECTED == "rejected"
    assert PENDING == "pending"
    assert ON_EXPIRY_APPROVE == "approve"
    assert ON_EXPIRY_REJECT == "reject"


# -- resolve_with_deadline: a decided gate passes through -----------------

def test_a_decided_resolution_passes_through_unchanged():
    # A resolved gate is never re-evaluated against the clock: an operator's
    # decision is final, deadline or not.
    for decided in (APPROVED, EDITED, REJECTED):
        assert resolve_with_deadline(
            decided, deadline=0.0, now=999.0, on_expiry=ON_EXPIRY_REJECT
        ) == decided


# -- resolve_with_deadline: pending against the deadline ------------------

def test_pending_with_no_deadline_stays_pending():
    # An unbounded gate never lapses: it waits for a human indefinitely.
    assert resolve_with_deadline(
        PENDING, deadline=None, now=10_000.0, on_expiry=ON_EXPIRY_REJECT
    ) == PENDING


def test_pending_before_the_deadline_stays_pending():
    assert resolve_with_deadline(
        PENDING, deadline=100.0, now=99.0, on_expiry=ON_EXPIRY_REJECT
    ) == PENDING


def test_pending_at_the_deadline_expires():
    # The forum boundary: now == deadline is not strictly-before, so it expires.
    assert resolve_with_deadline(
        PENDING, deadline=100.0, now=100.0, on_expiry=ON_EXPIRY_REJECT
    ) == REJECTED


def test_pending_past_the_deadline_expires():
    assert resolve_with_deadline(
        PENDING, deadline=100.0, now=100.5, on_expiry=ON_EXPIRY_REJECT
    ) == REJECTED


def test_expiry_decision_follows_on_expiry():
    # A gate raised with on_expiry=approve auto-approves when it lapses.
    assert resolve_with_deadline(
        PENDING, deadline=100.0, now=200.0, on_expiry=ON_EXPIRY_APPROVE
    ) == APPROVED


def test_expiry_defaults_to_reject_fail_closed():
    # A garbage on_expiry can only reach the kernel if a caller bypasses the
    # policy guard; the kernel still fails closed to reject, never approve.
    assert resolve_with_deadline(
        PENDING, deadline=100.0, now=200.0, on_expiry="banana"
    ) == REJECTED


# -- reconcile_action: only an approval writes ----------------------------

def test_only_approved_writes():
    assert reconcile_action(APPROVED) == ACTION_WRITE


def test_edited_rejected_pending_hold():
    assert reconcile_action(EDITED) == ACTION_HOLD
    assert reconcile_action(REJECTED) == ACTION_HOLD
    assert reconcile_action(PENDING) == ACTION_HOLD


def test_out_of_vocabulary_resolution_raises():
    # A resolution canon has no rule for is a wiring fault, not a silent hold.
    for bad in ("approved-ish", "", "APPROVED", None):
        try:
            reconcile_action(bad)
        except ValueError:
            continue
        raise AssertionError(f"reconcile_action must raise on {bad!r}")


# -- ConflictGatePolicy: the durable-deadline configuration ---------------

def test_default_policy_is_unbounded_and_rejects_on_lapse():
    policy = ConflictGatePolicy()
    assert policy.deadline_seconds is None
    assert policy.on_expiry == ON_EXPIRY_REJECT


def test_a_valid_bounded_policy_constructs():
    policy = ConflictGatePolicy(deadline_seconds=3600.0,
                                on_expiry=ON_EXPIRY_APPROVE)
    assert policy.deadline_seconds == 3600.0
    assert policy.on_expiry == ON_EXPIRY_APPROVE


def test_a_non_positive_deadline_is_refused():
    for bad in (0.0, -1.0):
        try:
            ConflictGatePolicy(deadline_seconds=bad)
        except ValueError:
            continue
        raise AssertionError(f"deadline_seconds {bad!r} must be refused")


def test_an_unknown_on_expiry_is_refused():
    try:
        ConflictGatePolicy(on_expiry="wait-forever")
    except ValueError:
        return
    raise AssertionError("an on_expiry outside the decision map must be refused")
