"""Tests for the DERIVED confidence valuation (Knuth-Skilling / Cox) beside the lattice.

The confidence layer is a SECONDARY [0,1] annotation on a DECIDED verdict. These tests
pin the four soundness invariants:
  * the combine is ASSOCIATIVE + commutative (the Cox/Knuth-Skilling axiom that forces
    the product rule) and consistent (identity = CERTAIN, absorbing = 0);
  * UNVERIFIABLE carries None (NOT 0.5) -- a non-probability, not "maximal uncertainty";
  * a confidence -- however high -- NEVER changes / promotes a verdict;
  * deterministic; and a soundness probe: no graded value yields a false VERIFIED.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product

import pytest

from coherence_membrane.certificate import Certificate, Verdict
from coherence_membrane.composition import compose
from coherence_membrane.confidence import (
    CERTAIN,
    Graded,
    annotate,
    combine,
    combine_all,
    compose_confident,
    confidence_of,
    grade,
)

_GRID = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)


def _v(conf=None, oracle="o"):
    return grade(Certificate("step", Verdict.VERIFIED, oracle), conf)


def _r(conf=None, oracle="o"):
    return grade(Certificate("step", Verdict.REFUTED, oracle), conf)


def _u(oracle="o"):
    return grade(Certificate("step", Verdict.UNVERIFIABLE, oracle), None)


# --- R4/R1: the combine is the associative Knuth-Skilling product ----------------------


def test_combine_is_associative():
    # the load-bearing Cox/Knuth-Skilling axiom: (p*q)*r == p*(q*r), exhaustively on a grid.
    for p, q, r in product(_GRID, repeat=3):
        left = combine(combine(p, q), r)
        right = combine(p, combine(q, r))
        assert left == pytest.approx(right)


def test_combine_is_commutative():
    for p, q in product(_GRID, repeat=2):
        assert combine(p, q) == pytest.approx(combine(q, p))


def test_combine_identity_and_absorbing():
    # CERTAIN (1.0) is the identity (composing away); 0.0 is absorbing (impossible step).
    for p in _GRID:
        assert combine(CERTAIN, p) == pytest.approx(p)
        assert combine(p, CERTAIN) == pytest.approx(p)
        assert combine(0.0, p) == 0.0
        assert combine(p, 0.0) == 0.0


def test_combine_is_the_product_rule():
    # the derived algebra IS multiplication (product rule, independent case) -- not invented.
    for p, q in product(_GRID, repeat=2):
        assert combine(p, q) == pytest.approx(p * q)


def test_combine_all_empty_is_certain_identity():
    # empty fold -> the identity, exactly as the lattice meet's empty fold is its top.
    assert combine_all([]) == CERTAIN
    assert combine_all([0.8]) == pytest.approx(0.8)
    assert combine_all([0.5, 0.5, 0.5]) == pytest.approx(0.125)


def test_combine_never_exceeds_either_input():
    # a conjunction is no MORE confident than any of its steps (monotone attenuation,
    # the confidence echo of the meet "result <= every input").
    for p, q in product(_GRID, repeat=2):
        c = combine(p, q)
        assert c <= p + 1e-12 and c <= q + 1e-12


def test_combine_rejects_out_of_range_and_nonreal():
    for bad in (-0.01, 1.01, float("inf"), float("nan"), None, "0.5", True):
        with pytest.raises(ValueError):
            combine(0.5, bad)
        with pytest.raises(ValueError):
            confidence_of(bad)


def test_confidence_of_accepts_exact_unit_endpoints_and_fraction():
    assert confidence_of(0) == 0.0
    assert confidence_of(1) == 1.0
    assert confidence_of(Fraction(1, 2)) == 0.5


# --- R2: UNVERIFIABLE carries None (not 0.5); decided verdicts carry a degree ----------


def test_unverifiable_carries_none_not_half():
    g = grade(Certificate("c", Verdict.UNVERIFIABLE, "o"), 0.9)
    assert g.confidence is None          # forced to None -- the no-witness rule
    assert g.confidence != 0.5           # explicitly NOT maximal-uncertainty p=0.5
    assert g.verdict is Verdict.UNVERIFIABLE


def test_graded_unverifiable_with_number_is_a_construction_error():
    # constructing a non-decided Graded WITH a confidence is a contradiction -> raises.
    with pytest.raises(ValueError):
        Graded(Certificate("c", Verdict.UNVERIFIABLE, "o"), 0.9)


def test_decided_verdict_carries_supplied_confidence():
    assert _v(0.8).confidence == pytest.approx(0.8)
    assert _r(0.3).confidence == pytest.approx(0.3)
    # a decided verdict with no grade supplied -> None (a grade was simply not given).
    assert _v(None).confidence is None


# --- R2/R5: confidence NEVER changes or promotes a verdict -----------------------------


def test_confidence_never_promotes_or_changes_a_verdict():
    for verdict in Verdict:
        cert = Certificate("c", verdict, "o")
        conf = None if verdict is Verdict.UNVERIFIABLE else 1.0
        g = grade(cert, conf)
        assert g.verdict is verdict                    # passed straight through
        assert g.certificate.verdict is verdict        # primary object untouched


def test_high_confidence_does_not_make_unverifiable_verified():
    # the soundness probe: the MAXIMUM confidence cannot lift a non-decided verdict.
    g = grade(Certificate("c", Verdict.UNVERIFIABLE, "o"), 1.0)
    assert g.verdict is Verdict.UNVERIFIABLE
    assert g.confidence is None


def test_annotate_is_additive_and_preserves_verdict():
    base = Certificate("c", Verdict.VERIFIED, "o", (("k", "v"),))
    out = annotate(base, 0.7)
    assert out.claim == base.claim and out.verdict is base.verdict and out.oracle == base.oracle
    assert out.evidence[:-1] == base.evidence           # original evidence intact
    assert dict(out.evidence)["confidence"] == repr(0.7)


def test_annotate_unverifiable_writes_none():
    out = annotate(Certificate("c", Verdict.UNVERIFIABLE, "o"), 0.99)
    assert out.verdict is Verdict.UNVERIFIABLE
    assert dict(out.evidence)["confidence"] == "none"   # never a number on UNVERIFIABLE


# --- compose_confident: the degree beside compose's verdict meet -----------------------


def test_compose_confident_multiplies_decided_graded_steps():
    # all-decided, all-graded -> the product (mirrors composing graded VERIFIED steps).
    assert compose_confident([_v(0.9), _v(0.8)]) == pytest.approx(0.72)
    assert compose_confident([_v(0.5), _r(0.5)]) == pytest.approx(0.25)


def test_compose_confident_none_when_any_step_unverifiable():
    # an UNVERIFIABLE step => the conjunction has no witness-backed degree (mirrors the
    # verdict meet attenuating to UNVERIFIABLE). The VERDICT side confirms it.
    steps = [_v(0.9), _u()]
    assert compose_confident(steps) is None
    assert compose([g.certificate for g in steps]).verdict is Verdict.UNVERIFIABLE


def test_compose_confident_none_when_a_decided_step_is_ungraded():
    # a decided-but-ungraded step makes the product undefined -> None (never assumed 1.0).
    assert compose_confident([_v(0.9), _v(None)]) is None


def test_compose_confident_empty_is_none():
    # empty graded argument -> None; the verdict layer already fails closed to UNVERIFIABLE.
    assert compose_confident([]) is None
    assert compose([]).verdict is Verdict.UNVERIFIABLE


def test_compose_confidence_is_associative_across_groupings():
    # confidence of a composed argument is grouping-independent (the product is associative),
    # matching the verdict meet's associativity -- the two layers move together.
    a, b, c = _v(0.9), _v(0.8), _v(0.5)
    whole = compose_confident([a, b, c])
    left = combine(compose_confident([a, b]), c.confidence)
    right = combine(a.confidence, compose_confident([b, c]))
    assert whole == pytest.approx(left) == pytest.approx(right)


# --- determinism -----------------------------------------------------------------------


def test_confidence_is_deterministic():
    a = compose_confident([_v(0.9), _v(0.8), _v(0.7)])
    b = compose_confident([_v(0.9), _v(0.8), _v(0.7)])
    assert a == b
    assert grade(Certificate("c", Verdict.VERIFIED, "o"), 0.42).to_dict() == \
        grade(Certificate("c", Verdict.VERIFIED, "o"), 0.42).to_dict()


def test_graded_to_dict_carries_confidence_beside_verdict():
    d = grade(Certificate("c", Verdict.VERIFIED, "o"), 0.6).to_dict()
    assert d["verdict"] == "verified" and d["confidence"] == pytest.approx(0.6)
    du = grade(Certificate("c", Verdict.UNVERIFIABLE, "o"), None).to_dict()
    assert du["verdict"] == "unverifiable" and du["confidence"] is None
