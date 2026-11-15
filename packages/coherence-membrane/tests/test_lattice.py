"""Formal verdict-lattice proofs, and their binding to the real adjudicators.

Two layers:
  * the abstract lattice laws (prove_all) -- exhaustive over the finite carriers;
  * the binding layer -- the actual functions (compare_drift, compare_composite)
    are proved to LAND IN the lattice (closure), to put their affirmative top
    behind positive evidence only (fail-closed reachability), and -- for the
    combined drift lattice -- to AGGREGATE EXACTLY as the lattice meet (monotonic
    attenuation: composition never launders a worse set into a better verdict).
"""

from __future__ import annotations

from itertools import product

import pytest

from coherence_membrane.composite import CompositeObservation, compare_composite
from coherence_membrane.lattice import (
    ALL_LATTICES,
    DRIFT_LATTICE,
    GRAPH_LATTICE,
    RECEIPT_LATTICE,
    prove_all,
    prove_lattice,
)
from coherence_membrane.observation import Observation, Provenance, Status
from coherence_membrane.phash import DRIFT, MATCH, UNVERIFIABLE, compare_drift

VERDICTS = (MATCH, DRIFT, UNVERIFIABLE)


# --- layer 1: the abstract laws (a complete decision procedure) -----------


def test_all_abstract_lattice_proofs_pass():
    proofs = prove_all()
    assert proofs, "expected at least one lattice proof"
    for p in proofs:
        assert p.ok, [c.to_dict() for c in p.failures()]


def test_each_lattice_is_bounded_with_unverifiable_in_the_middle():
    for L in (DRIFT_LATTICE, RECEIPT_LATTICE, GRAPH_LATTICE):
        assert prove_lattice(L).ok
        assert L.bottom != L.top
        assert UNVERIFIABLE in L.elements
        # UNVERIFIABLE is strictly between bottom and top: never the affirmative top.
        assert L.leq(L.bottom, UNVERIFIABLE) and L.leq(UNVERIFIABLE, L.top)
        assert UNVERIFIABLE not in (L.bottom, L.top)


def test_meet_matches_the_documented_drift_aggregation():
    # the table compare_composite implements: any DRIFT -> DRIFT; else any
    # UNVERIFIABLE -> UNVERIFIABLE; else MATCH. The meet must reproduce it.
    assert DRIFT_LATTICE.meet(MATCH, MATCH) == MATCH
    assert DRIFT_LATTICE.meet(MATCH, UNVERIFIABLE) == UNVERIFIABLE
    assert DRIFT_LATTICE.meet(UNVERIFIABLE, DRIFT) == DRIFT
    assert DRIFT_LATTICE.meet(MATCH, DRIFT) == DRIFT
    assert DRIFT_LATTICE.fold_meet([]) == MATCH  # identity is the top
    assert DRIFT_LATTICE.fold_meet([MATCH, MATCH, UNVERIFIABLE]) == UNVERIFIABLE
    assert DRIFT_LATTICE.fold_meet([MATCH, DRIFT, UNVERIFIABLE]) == DRIFT


# --- layer 2: binding compare_drift to the lattice ------------------------


def _drift(b_sha, c_sha, b_ph, c_ph):
    return compare_drift(b_sha, c_sha, b_ph, c_ph)


def test_compare_drift_closure_and_reachability():
    shas = (None, "", "a" * 64, "b" * 64)
    phs = (None, 0, 123)
    for b_sha, c_sha, b_ph, c_ph in product(shas, shas, phs, phs):
        v = _drift(b_sha, c_sha, b_ph, c_ph).verdict
        assert v in DRIFT_LATTICE.elements                      # closure
        if v == MATCH:                                          # reachability
            assert b_sha and b_sha == c_sha                     # only exact identity
        if v == DRIFT:
            assert b_sha and c_sha and b_sha != c_sha
            assert b_ph is not None and c_ph is not None
        if v == UNVERIFIABLE:
            assert (not b_sha or not c_sha) or (b_sha != c_sha and (b_ph is None or c_ph is None))
        # converse: exact byte identity is ALWAYS the affirmative top.
        if b_sha and b_sha == c_sha:
            assert v == MATCH


# --- layer 2: binding compare_composite to the lattice MEET ---------------


def _obs(organ: str, subject: str, identity: str | None, phash: str | None = None) -> Observation:
    data: dict = {}
    if identity is not None:
        data["identity_sha256"] = identity
    if phash is not None:
        data["perceptual_hash"] = phash
    return Observation(
        organ, subject, "", Status.PASS,
        Provenance.witness_bytes(subject, (identity or subject).encode(), "high"),
        data,
    )


def _component_pair(organ: str, subject: str, verdict: str):
    """A (baseline, current) component pair that compare_drift judges as `verdict`."""
    base = _obs(organ, subject, "a" * 64, "0" * 16)
    if verdict == MATCH:
        cur = _obs(organ, subject, "a" * 64, "0" * 16)        # identical identity
    elif verdict == DRIFT:
        cur = _obs(organ, subject, "b" * 64, "f" * 16)        # differ, both phash present
    elif verdict == UNVERIFIABLE:
        cur = _obs(organ, subject, "b" * 64, None)            # differ, current phash missing
    else:  # pragma: no cover - guard
        raise ValueError(verdict)
    return base, cur


def _assert_overall_is_meet_of_reported(baseline: CompositeObservation,
                                        current: CompositeObservation) -> str:
    """The central attenuation theorem: the overall verdict equals the lattice
    meet of the per-component verdicts the report actually emitted -- except an
    empty comparison, which fails closed to UNVERIFIABLE (strictly below the
    empty meet's identity, a safe tightening, never above it)."""
    report = compare_composite(baseline, current)
    assert report.verdict in DRIFT_LATTICE.elements            # closure
    reported = [c.verdict for c in report.components]
    if not reported:
        assert report.verdict == UNVERIFIABLE
        assert DRIFT_LATTICE.leq(report.verdict, MATCH)        # safe (<= the identity)
    else:
        assert report.verdict == DRIFT_LATTICE.fold_meet(reported)
    return report.verdict


def test_compare_composite_is_exactly_the_meet_over_all_verdict_vectors():
    # exhaustive over every per-modality verdict vector of length 1..4.
    for k in range(1, 5):
        for vector in product(VERDICTS, repeat=k):
            base_comps, cur_comps = [], []
            for i, verdict in enumerate(vector):
                b, c = _component_pair(f"org{i}", f"sub{i}", verdict)
                base_comps.append(b)
                cur_comps.append(c)
            baseline = CompositeObservation(components=base_comps)
            current = CompositeObservation(components=cur_comps)
            overall = _assert_overall_is_meet_of_reported(baseline, current)
            # and it equals the meet of the INTENDED per-modality verdicts.
            assert overall == DRIFT_LATTICE.fold_meet(vector)


def test_composite_empty_baseline_fails_closed_below_the_identity():
    overall = _assert_overall_is_meet_of_reported(
        CompositeObservation(components=[]),
        CompositeObservation(components=[_obs("o", "s", "a" * 64, "0" * 16)]),
    )
    assert overall == UNVERIFIABLE


def test_composite_missing_modality_attenuates_to_unverifiable():
    b0, c0 = _component_pair("vis", "f.png", MATCH)
    b1, _ = _component_pair("aud", "a.wav", MATCH)
    baseline = CompositeObservation(components=[b0, b1])
    current = CompositeObservation(components=[c0])             # aud went missing
    overall = _assert_overall_is_meet_of_reported(baseline, current)
    assert overall == UNVERIFIABLE                             # never a silent MATCH


def test_composite_extra_modality_attenuates_to_unverifiable():
    b0, c0 = _component_pair("vis", "f.png", MATCH)
    _, cx = _component_pair("aud", "a.wav", MATCH)
    baseline = CompositeObservation(components=[b0])
    current = CompositeObservation(components=[c0, cx])         # aud appeared unexpectedly
    overall = _assert_overall_is_meet_of_reported(baseline, current)
    assert overall == UNVERIFIABLE


def test_composite_duplicate_modality_attenuates_to_unverifiable():
    b0, c0 = _component_pair("vis", "f.png", MATCH)
    _, c0b = _component_pair("vis", "f.png", MATCH)            # duplicate key in current
    baseline = CompositeObservation(components=[b0])
    current = CompositeObservation(components=[c0, c0b])
    overall = _assert_overall_is_meet_of_reported(baseline, current)
    assert overall == UNVERIFIABLE                            # ambiguous -> fail closed


def test_one_drift_dominates_any_number_of_matches():
    # bottom is absorbing: a single confirmed change sinks the whole composite.
    base_comps, cur_comps = [], []
    for i in range(5):
        verdict = DRIFT if i == 2 else MATCH
        b, c = _component_pair(f"org{i}", f"sub{i}", verdict)
        base_comps.append(b)
        cur_comps.append(c)
    overall = _assert_overall_is_meet_of_reported(
        CompositeObservation(components=base_comps),
        CompositeObservation(components=cur_comps),
    )
    assert overall == DRIFT


# --- layer 0: the order-theoretic FOUNDATION, each law NAMED in code -------
#
# The verdict combinator is a BOUNDED MEET-SEMILATTICE (a frame, in the
# pointless-topology sense): a partial order with all finite meets and a top.
# `prove_meet_laws` already verifies every law by exhaustive enumeration (a
# complete decision procedure over the finite carrier), and
# `test_all_abstract_lattice_proofs_pass` checks them as one bundle. The tests
# below NAME each frame/lattice law as its own assertion -- so the foundation is
# not merely enumerated but cited and individually pinned in the test suite:
# commutativity, associativity, idempotency, monotonicity, absorption (top
# identity + bottom absorbing), and the boundedness that makes UNVERIFIABLE the
# fail-closed "no evidence" element strictly below the affirmative top.
#
# Foundation + attribution (study + cite, never strip): a frame / locale is a
# bounded lattice with the requisite (here finite) meets; see Johnstone, *Stone
# Spaces* (frames/locales), framed accessibly by 3cycle, '"Pointless"
# Topologies' (id `bhcNGkZmiVk`). The verdict structure being a frame makes
# "meet, never a false VERIFIED" a lattice-theoretic FACT with a reference,
# not an assertion. No runtime / verdict-semantics change -- naming only.
#
# NOTE on the bottom: in the SHIPPED lattices the bottom (absorbing) element is
# the positive-detection verdict (REFUTED/DRIFT/BROKEN) -- "a positive
# detection dominates" -- and UNVERIFIABLE sits strictly in the MIDDLE as the
# fail-closed absence-of-evidence element (never the affirmative top). This is
# the structure the enumeration proves; the named tests below assert exactly it.


@pytest.mark.parametrize("L", ALL_LATTICES, ids=lambda L: L.name)
def test_law_commutativity(L):
    # meet is commutative: a /\ b == b /\ a (order of evidence is irrelevant).
    for a, b in product(L.elements, repeat=2):
        assert L.meet(a, b) == L.meet(b, a)


@pytest.mark.parametrize("L", ALL_LATTICES, ids=lambda L: L.name)
def test_law_associativity(L):
    # meet is associative: (a /\ b) /\ c == a /\ (b /\ c) -- aggregation is grouping-free.
    for a, b, c in product(L.elements, repeat=3):
        assert L.meet(L.meet(a, b), c) == L.meet(a, L.meet(b, c))


@pytest.mark.parametrize("L", ALL_LATTICES, ids=lambda L: L.name)
def test_law_idempotency(L):
    # meet is idempotent: a /\ a == a (re-observing the same verdict adds nothing).
    for a in L.elements:
        assert L.meet(a, a) == a


@pytest.mark.parametrize("L", ALL_LATTICES, ids=lambda L: L.name)
def test_law_monotonicity(L):
    # meet is MONOTONE: degrading either input never improves the meet -- the
    # frame-morphism property that forbids laundering a worse observation into a
    # better verdict. a<=a' and b<=b'  =>  (a /\ b) <= (a' /\ b').
    for a, ap, b, bp in product(L.elements, repeat=4):
        if L.leq(a, ap) and L.leq(b, bp):
            assert L.leq(L.meet(a, b), L.meet(ap, bp))


@pytest.mark.parametrize("L", ALL_LATTICES, ids=lambda L: L.name)
def test_law_absorption_top_identity_and_bottom_absorbing(L):
    # ABSORPTION (the bounded-semilattice boundary laws):
    #   * the TOP (affirmative VERIFIED) is the meet identity -- it composes away;
    #   * the BOTTOM (a positive detection) is ABSORBING -- it dominates the meet.
    for a in L.elements:
        assert L.meet(L.top, a) == a              # top identity
        assert L.meet(L.bottom, a) == L.bottom    # bottom absorbing
    # the classic absorption identity a /\ (a \/ b) == a (uses join + meet).
    for a, b in product(L.elements, repeat=2):
        assert L.meet(a, L.join(a, b)) == a


@pytest.mark.parametrize("L", ALL_LATTICES, ids=lambda L: L.name)
def test_law_bounded_unverifiable_failclosed_below_top(L):
    # BOUNDEDNESS with the fail-closed discipline: there is a top and a bottom, and
    # UNVERIFIABLE is strictly BELOW the affirmative top (it can never BE the verdict a
    # gate may allow on) -- the order-theoretic statement of "UNVERIFIABLE first".
    assert all(L.leq(L.bottom, a) and L.leq(a, L.top) for a in L.elements)
    assert UNVERIFIABLE in L.elements
    assert L.leq(UNVERIFIABLE, L.top) and UNVERIFIABLE != L.top      # strictly below top
    assert L.meet(UNVERIFIABLE, L.top) == UNVERIFIABLE              # never lifts to the top


def test_named_laws_match_the_enumerated_proof():
    # the named per-law tests above and the exhaustive enumeration agree: this is the
    # SAME foundation, named here and machine-checked there (R2 -- not a second algebra).
    for L in ALL_LATTICES:
        assert prove_lattice(L).ok
