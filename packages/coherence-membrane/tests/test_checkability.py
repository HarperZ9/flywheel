"""Tests for bounded_checkability -- the re-check-cost budget guard (downgrade-only).

The guard makes "re-checkable proof" mean re-checkable IN PRACTICE: a sound VERIFIED
whose witness is too expensive (or whose cost is unknown) under an injected budget is
UNVERIFIABLE-in-practice, never VERIFIED. These tests pin: over-budget downgrades; a
cheap one is preserved; unknown cost under a finite budget fails closed; the budget is
injected (a larger budget keeps it); REFUTED/UNVERIFIABLE pass through; determinism;
and the soundness probe -- it is downgrade-only and never manufactures a VERIFIED.
"""
from __future__ import annotations

import pytest

from coherence_membrane.certificate import Certificate, Verdict
from coherence_membrane.checkability import (
    RECHECK_COST_KEY,
    bounded_checkability,
    recheck_cost_of,
    with_recheck_cost,
)


def _cert(verdict=Verdict.VERIFIED, cost=None, oracle="lra-fm-v1", evidence=()):
    ev = tuple(evidence)
    if cost is not None:
        ev = ev + ((RECHECK_COST_KEY, repr(float(cost))),)
    return Certificate("the claim", verdict, oracle, ev)


# --- cost parsing ----------------------------------------------------------------------


def test_recheck_cost_read_from_evidence():
    assert recheck_cost_of(_cert(cost=42)) == 42.0
    assert recheck_cost_of(_cert(cost=0)) == 0.0


def test_recheck_cost_absent_or_garbage_is_none():
    assert recheck_cost_of(_cert()) is None                                   # absent
    assert recheck_cost_of(Certificate("c", Verdict.VERIFIED, "o",
                                       ((RECHECK_COST_KEY, "not-a-number"),))) is None
    assert recheck_cost_of(Certificate("c", Verdict.VERIFIED, "o",
                                       ((RECHECK_COST_KEY, "-3"),))) is None   # negative
    assert recheck_cost_of(Certificate("c", Verdict.VERIFIED, "o",
                                       ((RECHECK_COST_KEY, "inf"),))) is None  # non-finite


def test_with_recheck_cost_is_additive_and_validated():
    base = _cert(evidence=(("k", "v"),))
    out = with_recheck_cost(base, 7)
    assert out.claim == base.claim and out.verdict is base.verdict and out.oracle == base.oracle
    assert out.evidence[:-1] == base.evidence
    assert recheck_cost_of(out) == 7.0
    for bad in (-1, float("inf"), float("nan"), "5", True):
        with pytest.raises(ValueError):
            with_recheck_cost(base, bad)


# --- R2: the downgrade rule ------------------------------------------------------------


def test_over_budget_verified_downgrades_to_unverifiable():
    out = bounded_checkability(_cert(cost=100), budget=10)
    assert out.verdict is Verdict.UNVERIFIABLE
    ev = dict(out.evidence)
    assert "unverifiable-in-practice" in ev["reason"]
    assert ev["downgraded_from"] == "verified"


def test_cheap_verified_is_preserved():
    out = bounded_checkability(_cert(cost=5), budget=10)
    assert out.verdict is Verdict.VERIFIED                          # STRONG: stays verified
    assert dict(out.evidence)["checkability"].startswith("strong")


def test_exactly_at_budget_is_preserved():
    # cost == budget is WITHIN budget (re-checkable exactly within the bound).
    assert bounded_checkability(_cert(cost=10), budget=10).verdict is Verdict.VERIFIED


def test_unknown_cost_under_finite_budget_fails_closed():
    # R4: absent cost under a finite budget -> UNVERIFIABLE (cannot bound re-checkability).
    out = bounded_checkability(_cert(cost=None), budget=10)
    assert out.verdict is Verdict.UNVERIFIABLE
    assert "unknown" in dict(out.evidence)["reason"]


def test_infinite_budget_is_the_explicit_optout():
    # an unbounded budget says "re-check cost is not a constraint" -> VERIFIED survives,
    # even with an unknown cost (the opt-out is explicit, not a silent default).
    assert bounded_checkability(_cert(cost=10**9), budget=float("inf")).verdict is Verdict.VERIFIED
    assert bounded_checkability(_cert(cost=None), budget=float("inf")).verdict is Verdict.VERIFIED


def test_uninterpretable_budget_fails_closed():
    # a NaN / non-real / negative budget cannot license a re-check -> downgrade (fail-closed).
    for bad in (float("nan"), -1, "10", None):
        assert bounded_checkability(_cert(cost=1), budget=bad).verdict is Verdict.UNVERIFIABLE


# --- R2: never upgrades; REFUTED / UNVERIFIABLE pass through ----------------------------


def test_refuted_passes_through_unchanged():
    c = _cert(verdict=Verdict.REFUTED, cost=10**9)
    assert bounded_checkability(c, budget=1) is c                   # identical object, untouched


def test_unverifiable_passes_through_unchanged():
    c = _cert(verdict=Verdict.UNVERIFIABLE)
    assert bounded_checkability(c, budget=1) is c


def test_never_upgrades_a_non_verified():
    # the soundness core: NOTHING that is not already VERIFIED can become VERIFIED here,
    # for ANY budget (including the infinite opt-out).
    for verdict in (Verdict.REFUTED, Verdict.UNVERIFIABLE):
        for budget in (0, 10, float("inf")):
            assert bounded_checkability(_cert(verdict=verdict, cost=1), budget=budget).verdict is verdict


def test_downgrade_only_soundness_probe_over_budget_grid():
    # exhaustive-ish probe: a VERIFIED either STAYS verified (cost present & <= budget)
    # or DOWNGRADES to UNVERIFIABLE -- it is NEVER turned into anything else, and a
    # non-VERIFIED is never lifted. No path produces a false/forged VERIFIED.
    budgets = [0, 1, 5, 10, 50, float("inf")]
    costs = [None, 0, 1, 5, 10, 50, 100]
    for budget in budgets:
        for cost in costs:
            out = bounded_checkability(_cert(cost=cost), budget=budget)
            assert out.verdict in (Verdict.VERIFIED, Verdict.UNVERIFIABLE)
            if out.verdict is Verdict.VERIFIED:
                # survival is justified ONLY by: infinite budget, or a known cost <= budget.
                assert budget == float("inf") or (cost is not None and cost <= budget)


def test_total_never_raises_on_malformed_certificate():
    # a malformed certificate (bad evidence shape) degrades to UNVERIFIABLE, never raises.
    class _Bad:
        verdict = Verdict.VERIFIED
        claim = "x"
        oracle = "o"
        evidence = "not-a-tuple-of-pairs"
    out = bounded_checkability(_Bad(), budget=1)
    assert out.verdict is Verdict.UNVERIFIABLE


# --- determinism -----------------------------------------------------------------------


def test_deterministic():
    a = bounded_checkability(_cert(cost=100), budget=10)
    b = bounded_checkability(_cert(cost=100), budget=10)
    assert a.to_dict() == b.to_dict()


# --- the strong/weak naming (R3 of the checkability spec) ------------------------------


def test_strong_weak_distinction_named_in_evidence():
    strong = bounded_checkability(_cert(cost=1), budget=10)
    weak = bounded_checkability(_cert(cost=1000), budget=10)
    assert dict(strong.evidence)["checkability"].startswith("strong")
    assert dict(weak.evidence)["checkability"].startswith("weak")
