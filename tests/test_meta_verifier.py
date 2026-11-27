# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""Unit and planted fail-closed trap tests for harness.meta_verifier (25 tests)."""
from __future__ import annotations

import pytest

from harness.meta_verifier import (
    DisclosureMechanism,
    EvidenceBand,
    audit_calibration_batch,
    conditional_entropy_bits,
    evaluate_confidence_calibration,
    evaluate_disclosure_equilibrium,
    extract_certainty_band,
    min_deterrence_audit_prob,
    run_meta_verifier_suite,
    shannon_entropy_bits,
    simulate_disclosure_rounds,
    verify_lossless_bijection,
)


# --- D6 Isomorphism Entropy & Lossless Bijection tests (8) ---


def test_d6_lossless_bijection_has_zero_conditional_entropy() -> None:
    samples = [{"id": i, "tag": f"k{i}"} for i in range(16)]
    v = verify_lossless_bijection(samples, lambda d: (d["id"], d["tag"]), lambda t: {"id": t[0], "tag": t[1]})
    assert v.ok and v.verdict == "PASS"
    assert v.input_entropy_bits == pytest.approx(4.0, abs=1e-6)
    assert v.output_entropy_bits == pytest.approx(4.0, abs=1e-6)
    assert v.conditional_entropy_bits == 0.0
    assert v.collisions == 0 and v.roundtrip_mismatches == 0


def test_d6_catches_many_to_one_lossy_projection_fail_closed() -> None:
    samples = list(range(16))
    v = verify_lossless_bijection(samples, lambda x: x % 4, lambda y: y)
    assert not v.ok and v.verdict == "REJECT"
    assert v.conditional_entropy_bits == pytest.approx(2.0, abs=1e-6)
    assert v.collisions == 12
    assert any("lossy_projection_collisions" in e for e in v.errors)
    assert any("nonzero_conditional_entropy" in e for e in v.errors)


def test_d6_catches_broken_inverse_despite_injective_encoding() -> None:
    samples = ["a", "b", "c", "d"]
    v = verify_lossless_bijection(samples, lambda s: s.upper(), lambda s: s)
    assert not v.ok and v.collisions == 0 and v.roundtrip_mismatches == 4
    assert any("roundtrip_mismatches" in e for e in v.errors)


def test_d6_catches_empty_sample_set_and_encode_exception() -> None:
    empty = verify_lossless_bijection([], lambda x: x, lambda x: x)
    assert not empty.ok and "empty_sample_set" in empty.errors

    def bad_enc(x: int) -> int:
        if x == 2:
            raise RuntimeError("boom")
        return x

    err = verify_lossless_bijection([0, 1, 2], bad_enc, lambda y: y)
    assert not err.ok and any("encode_error" in e for e in err.errors)


def test_d6_shannon_and_conditional_entropy_exact_identities() -> None:
    assert shannon_entropy_bits([0, 1, 0, 1]) == pytest.approx(1.0, abs=1e-9)
    assert shannon_entropy_bits([7, 7, 7]) == 0.0
    assert conditional_entropy_bits([0, 1, 2, 3], [0, 0, 1, 1]) == pytest.approx(1.0, abs=1e-9)


def test_d6_conditional_entropy_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        conditional_entropy_bits([1, 2], [1])


def test_d6_constant_projection_loses_full_input_entropy() -> None:
    samples = list(range(8))
    v = verify_lossless_bijection(samples, lambda _: "const", lambda _: 0)
    assert not v.ok and v.conditional_entropy_bits == pytest.approx(3.0, abs=1e-6)


def test_d6_decode_exception_caught_fail_closed() -> None:
    def bad_dec(_: str) -> str:
        raise ValueError("corrupt")

    v = verify_lossless_bijection(["x", "y"], lambda s: s, bad_dec)
    assert not v.ok and any("decode_error" in e for e in v.errors)


# --- N30 Linguistic Certainty vs Evidence Calibration tests (8) ---


def test_n30_high_certainty_passes_with_strong_calibrated_evidence() -> None:
    ev = EvidenceBand(empirical_accuracy=0.98, sample_size=24, ece=0.02)
    v = evaluate_confidence_calibration("The oracle proves exact bit-level parity.", ev)
    assert v.ok and v.verdict == "PASS" and v.linguistic_band == "high" and v.overclaim_gap == 0.0


def test_n30_catches_overclaimed_high_certainty_on_weak_accuracy() -> None:
    ev = EvidenceBand(empirical_accuracy=0.60, sample_size=20, ece=0.02)
    v = evaluate_confidence_calibration("This result is guaranteed to hold.", ev)
    assert not v.ok and v.verdict == "REJECT" and v.overclaim_gap == pytest.approx(0.35, abs=1e-6)
    assert any("overclaimed_high_accuracy" in e for e in v.errors)


def test_n30_catches_overclaimed_high_certainty_on_small_sample_or_high_ece() -> None:
    small = evaluate_confidence_calibration("Proven exact.", EvidenceBand(0.99, sample_size=3, ece=0.01))
    high_ece = evaluate_confidence_calibration("Proven exact.", EvidenceBand(0.99, sample_size=20, ece=0.15))
    assert not small.ok and any("overclaimed_high_sample_size" in e for e in small.errors)
    assert not high_ece.ok and any("overclaimed_high_ece" in e for e in high_ece.errors)


def test_n30_moderate_and_hedged_bands_calibrate_appropriately() -> None:
    mod_ok = evaluate_confidence_calibration("Evidence strongly indicates improvement.", EvidenceBand(0.82, 10, 0.05))
    mod_bad = evaluate_confidence_calibration("This likely holds.", EvidenceBand(0.50, 10, 0.05))
    hedge_ok = evaluate_confidence_calibration("Preliminary results suggest a gain.", EvidenceBand(0.55, 4, 0.10))
    assert mod_ok.ok and mod_ok.linguistic_band == "moderate"
    assert not mod_bad.ok
    assert hedge_ok.ok and hedge_ok.linguistic_band == "hedged"


def test_n30_extracts_strongest_certainty_band_when_mixed() -> None:
    band, terms = extract_certainty_band("This might look preliminary, yet it is 100% certain.")
    assert band == "high" and "100% certain" in terms


def test_n30_rejects_empty_claim_and_invalid_evidence_bounds() -> None:
    v = evaluate_confidence_calibration("   ", EvidenceBand(1.5, sample_size=0, ece=-0.1))
    assert not v.ok
    assert "empty_claim_text" in v.errors
    assert "invalid_empirical_accuracy" in v.errors
    assert "non_positive_sample_size" in v.errors
    assert "invalid_ece" in v.errors


def test_n30_batch_audit_rejects_empty_and_overclaimed_entries() -> None:
    good = ("Preliminary trace suggests parity.", EvidenceBand(0.65, 5, 0.08))
    bad = ("Guaranteed zero failures.", EvidenceBand(0.40, 5, 0.25))
    assert audit_calibration_batch([good])["ok"] is True
    assert audit_calibration_batch([])["ok"] is False
    mix = audit_calibration_batch([good, bad])
    assert not mix["ok"] and mix["rejected_indices"] == [1]


def test_n30_neutral_factual_statement_defaults_to_hedged_band() -> None:
    band, terms = extract_certainty_band("Latency measured 6.85 ms on host CPU.")
    assert band == "hedged" and terms == ()


# --- N71 Disclosure Penalty & Honest-Reporting Equilibrium tests (9) ---


def test_n71_strictly_honest_equilibrium_passes() -> None:
    mech = DisclosureMechanism(base_reward=100.0, fix_cost=8.0, audit_prob=0.25, penalty_fine=40.0, clawback_fraction=0.5)
    eq = evaluate_disclosure_equilibrium(mech)
    assert eq.ok and eq.verdict == "PASS"
    assert eq.dominant_strategy == "HONEST_DISCLOSURE"
    assert eq.honest_advantage == pytest.approx(14.5, abs=1e-6)
    assert eq.min_deterrence_audit_prob == pytest.approx(8.0 / 90.0, abs=1e-5)


def test_n71_catches_profitable_concealment_regime_fail_closed() -> None:
    mech = DisclosureMechanism(base_reward=100.0, fix_cost=25.0, audit_prob=0.05, penalty_fine=20.0, clawback_fraction=0.0)
    eq = evaluate_disclosure_equilibrium(mech)
    assert not eq.ok and eq.verdict == "REJECT"
    assert eq.dominant_strategy == "CONCEALMENT"
    assert eq.honest_advantage < 0.0
    assert any("profitable_concealment_regime" in e for e in eq.errors)


def test_n71_catches_zero_audit_probability_trap() -> None:
    mech = DisclosureMechanism(base_reward=100.0, fix_cost=5.0, audit_prob=0.0, penalty_fine=500.0)
    eq = evaluate_disclosure_equilibrium(mech)
    assert not eq.ok and "zero_audit_probability_enables_concealment" in eq.errors


def test_n71_catches_knife_edge_indifference_fail_closed() -> None:
    mech = DisclosureMechanism(base_reward=100.0, fix_cost=10.0, audit_prob=0.2, penalty_fine=50.0)
    eq = evaluate_disclosure_equilibrium(mech)
    assert not eq.ok and eq.honest_advantage == 0.0


def test_n71_rejects_invalid_mechanism_parameters() -> None:
    bad = DisclosureMechanism(base_reward=-1.0, fix_cost=-2.0, audit_prob=1.5, penalty_fine=-5.0, clawback_fraction=2.0, honest_bonus=-1.0)
    eq = evaluate_disclosure_equilibrium(bad)
    assert not eq.ok and len(eq.errors) == 6


def test_n71_min_deterrence_threshold_edge_cases() -> None:
    free = DisclosureMechanism(base_reward=100.0, fix_cost=5.0, audit_prob=0.1, penalty_fine=50.0, honest_bonus=5.0)
    zero_pen = DisclosureMechanism(base_reward=100.0, fix_cost=5.0, audit_prob=0.5, penalty_fine=0.0)
    assert min_deterrence_audit_prob(free) == 0.0
    assert min_deterrence_audit_prob(zero_pen) == 1.0


def test_n71_round_simulation_verifies_realized_honest_dominance() -> None:
    mech = DisclosureMechanism(base_reward=100.0, fix_cost=8.0, audit_prob=0.25, penalty_fine=40.0, clawback_fraction=0.5)
    sim = simulate_disclosure_rounds(mech, rounds=100, seed=71)
    assert sim["ok"] is True and sim["realized_honest_advantage"] > 0.0 and sim["caught_count"] > 0


def test_n71_round_simulation_rejects_non_positive_rounds_and_bad_regime() -> None:
    good = DisclosureMechanism(base_reward=100.0, fix_cost=8.0, audit_prob=0.25, penalty_fine=40.0)
    bad = DisclosureMechanism(base_reward=100.0, fix_cost=25.0, audit_prob=0.05, penalty_fine=20.0)
    assert simulate_disclosure_rounds(good, rounds=0)["ok"] is False
    assert simulate_disclosure_rounds(bad, rounds=50)["ok"] is False


def test_unified_meta_verifier_suite_passes_all_three_planted_controls() -> None:
    rep = run_meta_verifier_suite()
    assert rep["ok"] is True and rep["verdict"] == "PASS"
    assert rep["controls_caught"] == 3 and rep["controls_total"] == 3
