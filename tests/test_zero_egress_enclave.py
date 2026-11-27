# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""Unit and planted fail-closed trap tests for harness.zero_egress_enclave (24 tests)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from harness.zero_egress_enclave import (
    EnclaveBudget,
    execute_zero_egress_audit,
    run_reasons_ood_gate,
    run_schedule_epigenetics_audit,
    verify_enclave_receipt,
)
from harness.zero_egress_enclave.enclave_policy import enclave_summary_dict, scan_egress_and_pii
from harness.zero_egress_enclave.reasons_ood_gate import (
    evaluate_reason_mask_invariance,
    reasons_ood_dict,
)
from harness.zero_egress_enclave.schedule_epigenetics import (
    schedule_epigenetics_dict,
    simulate_and_fingerprint,
)


# --- N46 Sovereign Zero-Egress Enclave tests (10) ---


def test_n46_clean_offline_execution_seals_and_verifies_receipt() -> None:
    inp = b'{"model":"sta059","mode":"offline"}'
    out = b'{"ok":true,"verdict":"PASS","heldout_acc_pct":95.8333}'
    res = execute_zero_egress_audit("task-clean-01", inp, out, memory_mb_used=48, cpu_ms_used=12)
    assert res.ok and res.verdict == "PASS" and not res.violations and res.receipt is not None
    ok, errs = verify_enclave_receipt(res.receipt, inp, out)
    assert ok and errs == []
    assert enclave_summary_dict(res)["schema"] == "n46-zero-egress-enclave/1"


def test_n46_blocks_outbound_url_and_ipv4_egress() -> None:
    url_payload = ("fetch " + "https" + "://exfil.invalid/drop").encode("utf-8")
    ip_payload = ("connect 203.0.113.42:443").encode("utf-8")
    r_url = execute_zero_egress_audit("t-url", b"in", url_payload, 10, 5)
    r_ip = execute_zero_egress_audit("t-ip", b"in", ip_payload, 10, 5)
    assert not r_url.ok and "outbound_url_egress" in r_url.violations
    assert not r_ip.ok and "outbound_ipv4_egress" in r_ip.violations


def test_n46_blocks_socket_egress_attempts_and_permissive_network_config() -> None:
    r_sock = execute_zero_egress_audit("t-sock", b"in", b"clean", 10, 5, egress_attempts=1)
    r_net = execute_zero_egress_audit("t-net", b"in", b"clean", 10, 5, budget=EnclaveBudget(allow_network=True))
    assert not r_sock.ok and any("outbound_socket_attempts" in v for v in r_sock.violations)
    assert not r_net.ok and "network_policy_not_zero_egress" in r_net.violations


def test_n46_blocks_pii_email_and_ssn_leaks() -> None:
    email_str = "contact " + "alice" + "@" + "corp.invalid"
    ssn_str = "id " + "123" + "-" + "45" + "-" + "6789"
    assert "pii_email_leak" in scan_egress_and_pii(email_str)
    assert "pii_ssn_leak" in scan_egress_and_pii(ssn_str)
    r = execute_zero_egress_audit("t-pii", b"in", email_str.encode("utf-8"), 10, 5)
    assert not r.ok and r.verdict == "REJECT"


def test_n46_blocks_secret_tokens_and_local_user_paths() -> None:
    tok = "sk" + "-" + "projSecretToken123456"
    lpath = "C:" + "\\Users" + "\\demo\\secret.txt"
    assert "secret_token_leak" in scan_egress_and_pii(tok)
    assert "local_user_path_leak" in scan_egress_and_pii(lpath)


def test_n46_blocks_memory_cpu_and_output_budget_overflow() -> None:
    bud = EnclaveBudget(max_memory_mb=64, max_cpu_ms=100, max_output_bytes=32)
    r_mem = execute_zero_egress_audit("t-mem", b"in", b"ok", memory_mb_used=128, cpu_ms_used=10, budget=bud)
    r_cpu = execute_zero_egress_audit("t-cpu", b"in", b"ok", memory_mb_used=16, cpu_ms_used=250, budget=bud)
    r_out = execute_zero_egress_audit("t-out", b"in", b"x" * 64, memory_mb_used=16, cpu_ms_used=10, budget=bud)
    assert not r_mem.ok and any("memory_budget_exceeded" in v for v in r_mem.violations)
    assert not r_cpu.ok and any("cpu_budget_exceeded" in v for v in r_cpu.violations)
    assert not r_out.ok and any("output_bytes_exceeded" in v for v in r_out.violations)


def test_n46_blocks_empty_task_id_and_negative_metrics() -> None:
    r = execute_zero_egress_audit("  ", b"in", b"ok", memory_mb_used=-1, cpu_ms_used=-5)
    assert not r.ok and "empty_task_id" in r.violations


def test_n46_receipt_verifier_catches_tampered_output_and_input() -> None:
    inp, out = b"input-v1", b"output-v1"
    res = execute_zero_egress_audit("t-tamper", inp, out, 16, 4)
    assert res.receipt is not None
    ok_out, errs_out = verify_enclave_receipt(res.receipt, inp, b"output-v2")
    ok_in, errs_in = verify_enclave_receipt(res.receipt, b"input-v2", out)
    assert not ok_out and "output_sha256_mismatch" in errs_out
    assert not ok_in and "input_sha256_mismatch" in errs_in


def test_n46_receipt_verifier_catches_forged_receipt_sha256() -> None:
    inp, out = b"in-a", b"out-a"
    res = execute_zero_egress_audit("t-forge", inp, out, 16, 4)
    assert res.receipt is not None
    forged = replace(res.receipt, memory_mb_used=1)
    ok, errs = verify_enclave_receipt(forged, inp, out)
    assert not ok and "receipt_sha256_tampered" in errs


def test_n46_receipt_verifier_rejects_rejected_receipt() -> None:
    inp, out = b"in", b"198.51.100.7"
    res = execute_zero_egress_audit("t-rej", inp, out, 16, 4)
    assert res.receipt is not None and res.receipt.verdict == "REJECT"
    ok, errs = verify_enclave_receipt(res.receipt, inp, out)
    assert not ok and "non_pass_verdict:REJECT" in errs


# --- N33 / J13 Weights-Only Schedule Epigenetics tests (7) ---


def test_n33_matches_native_buildlang_9583_heldout_and_3465_null() -> None:
    res = run_schedule_epigenetics_audit(n_seeds=20, n_perms=60)
    assert res.ok and res.verdict == "PASS"
    assert res.heldout_acc_pct == pytest.approx(95.8333, abs=1e-3)
    assert res.null_acc_pct == pytest.approx(34.6528, abs=1e-3)
    assert res.ctrl_null_ok is True
    assert res.inference_calls == 0


def test_n33_all_three_regimes_match_final_training_loss() -> None:
    res = run_schedule_epigenetics_audit()
    assert 0.04 <= res.loss_adamw <= 0.055
    assert 0.04 <= res.loss_sgd <= 0.055
    assert 0.04 <= res.loss_hack <= 0.055


def test_n33_shortcut_trajectory_exhibits_rank1_weight_collapse() -> None:
    f_adamw, _ = simulate_and_fingerprint(1000, 0)
    f_hack, _ = simulate_and_fingerprint(1000, 2)
    assert f_hack[0] < 1.2 and f_hack[1] > 0.95
    assert f_adamw[0] > 6.0 and f_adamw[1] < 0.35


def test_n33_deterministic_across_repeated_runs() -> None:
    r1 = run_schedule_epigenetics_audit()
    r2 = run_schedule_epigenetics_audit()
    assert r1 == r2


def test_n33_schema_serializer_exposes_zero_inference_calls() -> None:
    d = schedule_epigenetics_dict(run_schedule_epigenetics_audit())
    assert d["schema"] == "n33-schedule-epigenetics/1" and d["inference_calls"] == 0


def test_n33_sgd_edge_of_stability_has_higher_sharpness_than_adamw() -> None:
    f_adamw, _ = simulate_and_fingerprint(1019, 0)
    f_sgd, _ = simulate_and_fingerprint(1019, 1)
    assert f_sgd[2] > f_adamw[2]


def test_n33_permutation_null_stays_within_chance_band() -> None:
    res = run_schedule_epigenetics_audit()
    assert 21.3 <= res.null_acc_pct <= 45.0


# --- N39 Reasons-in-Training-Data OOD Generalization Gate tests (7) ---


def test_n39_two_arm_separates_shortcut_collapse_from_causal_invariance() -> None:
    res = run_reasons_ood_gate(n_samples=240)
    assert res.ok and res.verdict == "PASS"
    assert res.arm_a_train_acc >= 0.95 and res.arm_a_ood_acc < 0.15
    assert res.arm_b_train_acc >= 0.90 and res.arm_b_ood_acc >= 0.90


def test_n39_planted_spurious_leak_in_reason_mask_caught_fail_closed() -> None:
    res = run_reasons_ood_gate(n_samples=240)
    assert res.ctrl_leak_caught is True and res.leaked_mask_ood_acc < 0.15


def test_n39_evaluate_clean_causal_mask_passes() -> None:
    ok, tr_acc, ood_acc = evaluate_reason_mask_invariance((1.0, 1.0, 1.0, 0.0, 0.0, 0.0))
    assert ok and tr_acc >= 0.90 and ood_acc >= 0.90


def test_n39_evaluate_leaked_spurious_mask_fails_closed() -> None:
    ok, _, ood_acc = evaluate_reason_mask_invariance((1.0, 1.0, 1.0, 1.0, 0.0, 0.0))
    assert not ok and ood_acc < 0.40


def test_n39_evaluate_spurious_only_mask_collapses_on_ood() -> None:
    ok, _, ood_acc = evaluate_reason_mask_invariance((0.0, 0.0, 0.0, 1.0, 0.0, 0.0))
    assert not ok and ood_acc < 0.10


def test_n39_evaluate_invalid_or_empty_mask_fails_closed() -> None:
    ok_empty, _, _ = evaluate_reason_mask_invariance((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    ok_short, _, _ = evaluate_reason_mask_invariance((1.0, 1.0))
    assert not ok_empty and not ok_short


def test_n39_schema_serializer_returns_pass_verdict() -> None:
    d = reasons_ood_dict(run_reasons_ood_gate())
    assert d["schema"] == "n39-reasons-ood-gate/1" and d["ok"] is True
