"""CPU-safe unit tests & planted-failure controls for JFC-3P Wave 2 frontier modules.

Tests BitNet b1.58 ternary quantization, groupwise INT4 quantization, EAGLE-3
lossless speculative decoding (including planted corrupted-draft rejection),
and the L0..L4 Consumer-Hardware Frontier Parity Ladder. Pure stdlib Python.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

from harness.arch_lab import (
    Eagle3SpeculativeVerifier,
    bitnet_matvec,
    dequantize_bitnet_158,
    eval_frontier_ladder,
    int4_matvec,
    quantize_bitnet_158,
    quantize_int4_groupwise,
)
from harness.arch_lab.memory import matvec, rand_mat
from harness.harness_dynamics import evaluate_maintainability_debt


def test_bitnet_158_ternary_quantization_and_multiply_free_matvec() -> None:
    rng = random.Random(101)
    weights = rand_mat(32, 32, 0.4, rng)
    vec = [rng.uniform(-1.0, 1.0) for _ in range(32)]

    q = quantize_bitnet_158(weights)
    unique_codes = {v for row in q.codes for v in row}
    assert unique_codes.issubset({-1, 0, 1})
    assert q.metrics.compression_vs_fp32 > 18.0
    assert q.metrics.compression_vs_fp16 > 9.0
    assert q.metrics.cosine_fidelity > 0.85
    assert 0.1 < q.metrics.zero_fraction < 0.7

    y_fast = bitnet_matvec(q, vec)
    y_ref = matvec(dequantize_bitnet_158(q.codes, q.scale), vec)
    for a, b in zip(y_fast, y_ref):
        assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def test_groupwise_int4_quantization_fidelity_beats_ternary_at_high_compression() -> None:
    rng = random.Random(202)
    weights = rand_mat(32, 32, 0.5, rng)
    vec = [rng.uniform(-1.0, 1.0) for _ in range(32)]

    q158 = quantize_bitnet_158(weights)
    q4 = quantize_int4_groupwise(weights, group_size=16)

    assert all(-7 <= v <= 7 for row in q4.codes for v in row)
    assert q4.metrics.compression_vs_fp32 > 6.0
    assert q4.metrics.cosine_fidelity > 0.99
    assert q4.metrics.mse < q158.metrics.mse * 0.15
    assert q158.metrics.compression_vs_fp32 > q4.metrics.compression_vs_fp32 * 2.5

    y_q4 = int4_matvec(q4, vec)
    y_fp = matvec(weights, vec)
    err = math.sqrt(sum((a - b) ** 2 for a, b in zip(y_q4, y_fp)) / len(y_fp))
    assert err < 0.2


def test_eagle3_lossless_speculative_decoding_zero_divergence_and_speedup() -> None:
    vocab = 8

    def target_fn(seq):
        nxt = (sum(seq[-2:]) * 5 + len(seq)) % vocab
        p = [0.01 / (vocab - 1)] * vocab
        p[nxt] = 0.99
        return p

    def aligned_draft(seq):
        nxt = (sum(seq[-2:]) * 5 + len(seq)) % vocab
        q = [0.04 / (vocab - 1)] * vocab
        q[nxt] = 0.96
        return q

    verifier = Eagle3SpeculativeVerifier(draft_len=4, greedy=True)
    baseline = verifier.decode_autoregressive([2, 5], 25, target_fn)
    rep = verifier.decode_speculative([2, 5], 25, target_fn, aligned_draft)

    assert rep.divergence_count == 0
    assert rep.divergence_rate == 0.0
    assert list(rep.tokens) == baseline
    assert rep.effective_speedup >= 4.0
    assert rep.target_calls < len(baseline)


def test_planted_corrupted_draft_control_is_rejected_with_zero_divergence() -> None:
    vocab = 8

    def target_fn(seq):
        nxt = (len(seq) * 3 + seq[-1]) % (vocab - 1)  # never emits token 7
        p = [0.0] * vocab
        p[nxt] = 1.0
        return p

    def adversarial_draft(_seq):
        q = [0.0] * vocab
        q[7] = 1.0  # tampered forbidden token
        return q

    verifier = Eagle3SpeculativeVerifier(draft_len=4, greedy=True)
    rep = verifier.decode_speculative([1, 2], 16, target_fn, adversarial_draft, forbidden_tokens={7})

    assert rep.tampered_tokens_accepted == 0
    assert rep.accepted_draft_tokens == 0
    assert rep.rejected_draft_tokens == 16
    assert rep.divergence_count == 0
    assert 7 not in rep.tokens

    # Also verify stochastic rejection sampling rejects 0-probability tampered token 100%
    stoch = Eagle3SpeculativeVerifier(draft_len=4, greedy=False)
    rep_s = stoch.decode_speculative([1, 2], 16, target_fn, adversarial_draft, seed=99, forbidden_tokens={7})
    assert rep_s.tampered_tokens_accepted == 0
    assert 7 not in rep_s.tokens


def test_frontier_ladder_l0_to_l4_cpu_and_offline_fallback(tmp_path: Path) -> None:
    missing = tmp_path / "no_suite.json"
    report = eval_frontier_ladder(device="cpu", suite_bench_path=missing)
    assert report["schema"] == "jfc3p-frontier-ladder/1"
    assert report["all_passed"] is True
    assert [r["rung"] for r in report["rungs"]] == ["L0", "L1", "L2", "L3", "L4"]
    assert report["report_sha256"].startswith("sha256:")

    custom_suite = tmp_path / "bench.json"
    custom_suite.write_text(json.dumps({
        "ds03_formula_oracle": {"known_answer_pass_rate": 1.0, "planted_control_kill_rate": 1.0},
        "ds06_three_plate_oracle": {"three_plate_ABC": {"planted_defect_recall": 1.0, "false_accept_rate": 0.0}},
        "ds07_recall_benchmark_80": {"arms": {"workstation_recall_idf_compact": {
            "hit_at_5": 0.925, "mrr": 0.85, "median_latency_ms": 1.8, "avg_injected_tokens": 90.0
        }}},
    }), encoding="utf-8")
    live_rep = eval_frontier_ladder(device="cpu", suite_bench_path=custom_suite)
    assert live_rep["all_passed"] is True
    assert live_rep["rungs"][4]["metrics"]["source"] == "live_suite"


def test_all_arch_lab_and_frontier_files_pass_maintainability_debt_gate() -> None:
    root = Path(__file__).resolve().parent.parent
    files = list(sorted((root / "harness" / "arch_lab").glob("*.py"))) + [
        root / "tests" / "test_arch_lab_frontier.py"
    ]
    modules = {p.name: p.read_text(encoding="utf-8") for p in files}
    debt = evaluate_maintainability_debt(modules, max_file_lines=300, max_function_lines=50)
    assert debt["verdict"] == "ACCEPT", debt["violations"]
