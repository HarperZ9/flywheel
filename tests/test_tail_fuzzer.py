# SPDX-License-Identifier: MIT
"""Unit and adversarial tail-risk tests for harness.tail_fuzzer."""

from __future__ import annotations

import ast
import math
import os
import sys
from pathlib import Path

import pytest

from harness import tail_fuzzer as tf


def _safe_bounded_target(case: object) -> float:
    if isinstance(case, tf.BoundaryCase) and isinstance(case.value, float):
        if not math.isfinite(case.value):
            return 1.0
        return min(abs(case.value), 5.0) / 5.0
    return 0.5


def test_boundary_fuzzer_includes_all_extreme_edges_and_is_reproducible() -> None:
    cases = tf.generate_mixed_boundary_cases(seed=104, count=160)
    assert len(cases) == 160
    cats = {c.category for c in cases}
    assert {"extreme_float", "boundary_int", "adversarial_str", "empty_partition",
            "singleton_partition", "skewed_partition", "null_bytes"} <= cats
    assert tf.is_seed_reproducible(tf.generate_mixed_boundary_cases, seed=104, count=160) is True
    assert tf.is_seed_reproducible(tf.generate_float_tail_cases, seed=7, count=64) is True
    assert tf.fingerprint_cases(cases) != tf.fingerprint_cases(tf.generate_mixed_boundary_cases(seed=105, count=160))


@pytest.mark.parametrize("seed", [0, 1, 42, 9999])
def test_float_tail_generator_seed_invariance(seed: int) -> None:
    a = tf.generate_float_tail_cases(seed=seed, count=80)
    b = tf.generate_float_tail_cases(seed=seed, count=80)
    assert tf.fingerprint_cases(a) == tf.fingerprint_cases(b)
    assert any(isinstance(c.value, float) and math.isnan(c.value) for c in a)
    assert any(isinstance(c.value, float) and c.value == 0.0 and math.copysign(1.0, c.value) < 0 for c in a)


def test_tail_metrics_exact_quantiles_cvar_and_excursion() -> None:
    samples = [1.0] * 98 + [10.0, 20.0]
    m = tf.compute_tail_metrics(samples)
    assert m.sample_count == 100 and m.finite_count == 100 and m.non_finite_count == 0
    assert m.p50 == 1.0 and m.p99 > 10.0 and m.cvar_99 == 20.0 and m.max_val == 20.0
    assert m.max_excursion_ratio == 20.0 and m.to_dict()["cvar_99"] == 20.0


@pytest.mark.parametrize("bad_val", [float("nan"), float("inf"), float("-inf"), True, "bad"])
def test_tail_metrics_flags_non_finite_or_invalid_samples(bad_val: object) -> None:
    m = tf.compute_tail_metrics([1.0, 2.0, bad_val])
    assert m.non_finite_count == 1 and (m.has_nan or m.has_inf)


def test_tail_metrics_validation_errors() -> None:
    with pytest.raises(ValueError):
        tf.compute_tail_metrics([])
    with pytest.raises(ValueError):
        tf.compute_tail_metrics([1.0], alpha=1.5)
    with pytest.raises(ValueError):
        tf.quantile_sorted([], 0.5)
    with pytest.raises(ValueError):
        tf.quantile_sorted([1.0], -0.1)


def test_fuzz_gate_passes_clean_bounded_target_and_seals_deterministically() -> None:
    pol = tf.FuzzGatePolicy(max_p99=2.0, max_cvar_99=2.0, max_excursion_ratio=5.0)
    r1 = tf.run_tail_fuzz_gate(_safe_bounded_target, seed=42, count=200, invariant_fn=lambda _c, v: 0.0 <= v <= 1.0, policy=pol)
    r2 = tf.run_tail_fuzz_gate(_safe_bounded_target, seed=42, count=200, invariant_fn=lambda _c, v: 0.0 <= v <= 1.0, policy=pol)
    assert r1.passed is True and r1.cases_executed == 200 and r1.invariant_violations == 0
    assert r1.non_finite_count == 0 and r1.seed_reproducible is True
    assert r1.tail_fuzz_attestation_sha256 == r2.tail_fuzz_attestation_sha256
    assert r1.to_dict()["passed"] is True


def test_planted_control_1_hidden_p99_tail_blowup_caught_fail_closed() -> None:
    def _cliff_target(case: object) -> float:
        idx = case.case_id if isinstance(case, tf.BoundaryCase) else 0
        return 5000.0 if (idx % 100) >= 98 else 1.0

    pol = tf.FuzzGatePolicy(max_p99=50.0, max_cvar_99=100.0, max_excursion_ratio=200.0)
    rep = tf.run_tail_fuzz_gate(_cliff_target, seed=42, count=200, policy=pol)
    assert rep.passed is False
    assert any(r.startswith("P99_TAIL_BLOWUP:") for r in rep.reasons)
    assert any(r.startswith("CVAR_99_EXCEEDED:") for r in rep.reasons)
    assert any(r.startswith("MAX_EXCURSION_EXCEEDED:") for r in rep.reasons)


def test_planted_control_2_silent_nan_propagation_caught_fail_closed() -> None:
    def _nan_leaky(case: object) -> float:
        if isinstance(case, tf.BoundaryCase) and isinstance(case.value, float):
            return case.value * 0.0  # NaN/Inf * 0.0 -> NaN!
        return 0.5

    rep = tf.run_tail_fuzz_gate(_nan_leaky, tf.generate_float_tail_cases, seed=7, count=64)
    assert rep.passed is False and rep.non_finite_count >= 3
    assert any(r.startswith("SILENT_NAN_OR_INF_PROPAGATION:") for r in rep.reasons)


def test_planted_control_3_nondeterministic_unseeded_generator_caught_fail_closed() -> None:
    def _unseeded_gen(_seed: int, count: int) -> list[int]:
        return [int.from_bytes(os.urandom(4), "little") for _ in range(count)]

    rep = tf.run_tail_fuzz_gate(lambda _x: 1.0, _unseeded_gen, seed=42, count=32)
    assert rep.passed is False and rep.seed_reproducible is False
    assert "NON_DETERMINISTIC_GENERATOR" in rep.reasons


@pytest.mark.parametrize("bad_count", [0, -5])
def test_generators_reject_non_positive_count(bad_count: int) -> None:
    with pytest.raises(ValueError):
        tf.generate_float_tail_cases(1, bad_count)
    with pytest.raises(ValueError):
        tf.generate_mixed_boundary_cases(1, bad_count)


def test_fuzz_gate_counts_uncaught_exceptions_and_invariant_failures() -> None:
    def _crasher(case: object) -> float:
        if isinstance(case, tf.BoundaryCase) and case.case_id == 0:
            raise RuntimeError("boom")
        return 2.0

    rep = tf.run_tail_fuzz_gate(_crasher, seed=1, count=20, invariant_fn=lambda _c, v: v <= 1.0)
    assert rep.passed is False and rep.invariant_violations == 20
    assert any(r.startswith("INVARIANT_VIOLATIONS:") for r in rep.reasons)


@pytest.mark.parametrize("edge_val", [0.0, -0.0, 5e-324, float((1 << 53) + 1), float("nan"), float("inf")])
def test_extreme_ieee754_edge_values_present_and_fingerprinted(edge_val: float) -> None:
    fp = tf.fingerprint_cases([tf.BoundaryCase(0, "edge", edge_val)])
    assert len(fp) == 64
    assert fp == tf.fingerprint_cases([tf.BoundaryCase(0, "edge", edge_val)])


def test_package_hygiene_loc_spdx_stdlib_and_scope_limits() -> None:
    root = Path(__file__).resolve().parents[1]
    pkg_files = sorted((root / "harness" / "tail_fuzzer").glob("*.py"))
    assert len(pkg_files) == 4
    assert set(tf.HONEST_SCOPE_LIMITS) == {"boundary_fuzzer", "tail_metrics", "fuzz_gate"}
    for path in [*pkg_files, Path(__file__).resolve()]:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 250, f"{path.name} has {len(lines)} lines (> 250)"
        assert lines[0] == "# SPDX-License-Identifier: MIT"
        assert "\u2014" not in text and "\u2013" not in text
    for path in pkg_files:
        text = path.read_text(encoding="utf-8")
        assert "HONEST_SCOPE_LIMIT" in text
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] in sys.stdlib_module_names for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                assert node.module.split(".")[0] in sys.stdlib_module_names
