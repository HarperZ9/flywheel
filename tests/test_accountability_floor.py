# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""Unit and planted-attack tests for harness.accountability_floor (24 tests)."""
from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from harness.accountability_floor import (
    OutOfBandChain,
    evaluate_reseating_valve,
    evaluate_three_controls,
    run_closed_loop_rsi_audit,
    run_three_arm_valve_study,
    run_three_plate_audit_suite,
    simulate_rsi_arm,
    verify_binary_chain_32,
    verify_three_plate,
)
from harness.accountability_floor.anti_self_audit import SelfAttestationError
from harness.accountability_floor.planted_negatives import (
    plate1_surface,
    plate2_invariant,
    plate3_mutant_kill,
)


def _sha(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


# --- N25 Honest-Exit Reseating Valve tests (6) ---


def test_n25_valve_admits_oracle_verified_solvable_step() -> None:
    dec = evaluate_reseating_valve(True, True, True, step_cost=1.0, budget_remaining=5.0)
    assert dec.action == "ADMIT" and dec.admitted and not dec.fabricated


def test_n25_valve_zero_penalty_honest_abstain_on_unsolvable() -> None:
    dec = evaluate_reseating_valve(False, False, False, step_cost=1.0, budget_remaining=5.0, abstain_penalty=0.0)
    assert dec.action == "HONEST_ABSTAIN" and dec.abstained and not dec.admitted and not dec.fabricated


def test_n25_valve_blocks_planted_fabrication_on_unsolvable() -> None:
    dec = evaluate_reseating_valve(False, True, False, step_cost=1.0, budget_remaining=5.0, valve_enabled=True)
    assert dec.action == "FABRICATION_BLOCKED" and not dec.admitted and dec.fabricated


def test_n25_valve_disabled_admits_fabrication_control() -> None:
    dec = evaluate_reseating_valve(False, True, False, step_cost=1.0, budget_remaining=5.0, valve_enabled=False)
    assert dec.action == "FABRICATED_PASS" and dec.admitted and dec.fabricated


def test_n25_valve_enforces_budget_cap_and_rejects_negative_budget() -> None:
    halt = evaluate_reseating_valve(True, True, True, step_cost=10.0, budget_remaining=5.0)
    assert halt.action == "HALT_BUDGET" and not halt.admitted and halt.cost_spent == 0.0
    neg = evaluate_reseating_valve(True, True, True, step_cost=-1.0, budget_remaining=5.0)
    assert neg.action == "REJECT" and neg.reason == "invalid_negative_budget"


def test_n25_three_arm_study_separates_goodhart_from_harper_valve() -> None:
    res = run_three_arm_valve_study(n_solvable=40, n_unsolvable=20, budget_cap=60.0)
    assert res["ok"] is True
    assert res["arms"]["arm0_unguarded"]["fabrications"] == 20
    assert res["arms"]["arm2_harper_valve"]["fabrications"] == 0
    assert res["arms"]["arm2_harper_valve"]["honest_abstains"] == 20


# --- N28 Planted-Negatives & Moat 8 Three-Plate tests (6) ---


def test_n28_three_controls_pass_when_all_three_armed() -> None:
    suite = evaluate_three_controls(True, True, [0.33, 0.35, 0.34, 0.32])
    assert suite.ok and suite.verdict == "PASS" and not suite.failed_controls


def test_n28_three_controls_reject_false_pass_leak() -> None:
    suite = evaluate_three_controls(False, True, [0.33, 0.34])
    assert not suite.ok and "false_pass_not_caught" in suite.failed_controls


def test_n28_three_controls_reject_false_fail_and_leaking_null() -> None:
    suite = evaluate_three_controls(True, False, [0.85, 0.90])
    assert not suite.ok
    assert "false_fail_not_caught" in suite.failed_controls
    assert "permutation_null_out_of_band" in suite.failed_controls


def test_n28_three_controls_reject_empty_null_list() -> None:
    suite = evaluate_three_controls(True, True, [])
    assert not suite.ok and suite.verdict == "REJECT"


def test_moat8_three_plate_rejects_planted_2of3_bypass_and_faults() -> None:
    assert verify_three_plate(plate1_surface(16, 0, 0), plate2_invariant(0, 10), plate3_mutant_kill(3, 3, 1)) == 0
    assert verify_three_plate(1, 1, 0) == -801
    assert verify_three_plate(0, 1, 1) == -802
    assert verify_three_plate(1, 0, 1) == -803
    assert verify_three_plate(0, 0, 0) == -804
    assert verify_three_plate(1, 1, 1, n28_controls=2) == -806


def test_moat8_64_case_audit_suite_100pct_recall_zero_false_accepts() -> None:
    res = run_three_plate_audit_suite()
    assert res["ok"] is True
    assert res["tp"] == 32 and res["tn"] == 32
    assert res["false_accepts"] == 0 and res["false_rejects"] == 0
    assert res["three_plate_recall"] == 1.0


# --- N49 Anti-Self-Investigation SHA-256 Chain tests (6) ---


def test_n49_chain_accepts_independent_verifier_and_verifies_offline() -> None:
    chain = OutOfBandChain()
    chain.append("proposer-alpha", "verifier-beta", _sha("claim-1"))
    chain.append("proposer-alpha", "verifier-gamma", _sha("claim-2"))
    ok, errs = OutOfBandChain.verify_records(chain.records)
    assert ok and errs == [] and len(chain.records) == 2


def test_n49_chain_rejects_self_attestation_case_insensitive() -> None:
    chain = OutOfBandChain()
    with pytest.raises(SelfAttestationError):
        chain.append("agent-a", "Agent-A", _sha("self-graded"))


def test_n49_chain_rejects_empty_identities_and_bad_digest() -> None:
    chain = OutOfBandChain()
    with pytest.raises(SelfAttestationError):
        chain.append("agent-a", "   ", _sha("missing-verifier"))
    with pytest.raises(ValueError):
        chain.append("agent-a", "agent-b", "not-a-sha256")


def test_n49_chain_catches_tampered_payload_digest() -> None:
    chain = OutOfBandChain()
    rec = chain.append("proposer-1", "verifier-2", _sha("original"))
    tampered = replace(rec, claim_digest=_sha("forged"))
    ok, errs = OutOfBandChain.verify_records([tampered])
    assert not ok and any("tampered" in e for e in errs)


def test_n49_chain_catches_reordered_or_self_attested_records() -> None:
    chain = OutOfBandChain()
    r0 = chain.append("p1", "v1", _sha("c0"))
    r1 = chain.append("p1", "v2", _sha("c1"))
    ok_swap, errs_swap = OutOfBandChain.verify_records([r1, r0])
    assert not ok_swap and errs_swap
    forged_self = replace(r0, verifier_id="p1")
    ok_self, errs_self = OutOfBandChain.verify_records([forged_self])
    assert not ok_self and any("self-attestation" in e for e in errs_self)


def test_n49_binary_32_step_chain_matches_native_buildlang_digest() -> None:
    res = verify_binary_chain_32(32)
    assert res["chain_sha"] == "sha256:12fa00be72d19ec6f070a782e0eafc8c9de6c8f66cef3d6e533f385ff204544e"


# --- STA-070 Closed-Loop RSI Auditor tests (6) ---


def test_sta070_arm_a_reproduces_goodhart_collapse() -> None:
    arm_a = simulate_rsi_arm(False, False, False, False)
    assert arm_a.true_cap == pytest.approx(-4.0, abs=1e-6)
    assert arm_a.fake_score == pytest.approx(81.0, abs=1e-6)
    assert arm_a.hacks_accepted == 180 and not arm_a.monotone


def test_sta070_arm_b_achieves_monotone_8953x_and_native_sha_parity() -> None:
    arm_b = simulate_rsi_arm(True, True, True, True)
    assert arm_b.monotone is True
    assert arm_b.true_cap == pytest.approx(8.953, abs=1e-3)
    assert arm_b.hacks_accepted == 0
    assert arm_b.honest_abstains == 20
    assert arm_b.verified_tools == 80
    assert arm_b.chain_sha_prefix == "sha256:2f2c9ab2abdcd16b85c5409c0de4ddab"


def test_sta070_planted_control_disabled_oracle_admits_80_overt_hacks() -> None:
    ctrl = simulate_rsi_arm(False, True, True, True)
    assert ctrl.hacks_accepted == 80


def test_sta070_planted_control_disabled_valve_fabricates_20_probes() -> None:
    ctrl = simulate_rsi_arm(True, True, False, True)
    assert ctrl.hacks_accepted == 20 and ctrl.honest_abstains == 0


def test_sta070_planted_control_bypassed_epigenetics_admits_80_shortcuts() -> None:
    ctrl = simulate_rsi_arm(True, True, True, False)
    assert ctrl.hacks_accepted == 80


def test_sta070_unified_audit_passes_all_three_planted_controls() -> None:
    rep = run_closed_loop_rsi_audit()
    assert rep["ok"] is True and rep["verdict"] == "PASS"
    assert rep["controls_caught"] == 3 and rep["controls_total"] == 3
