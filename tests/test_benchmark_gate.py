# SPDX-License-Identifier: MIT
"""Unit and adversarial tamper tests for harness.benchmark_gate."""

from __future__ import annotations

import ast
import copy
import json
import sys
from pathlib import Path

import pytest

from harness import benchmark_gate as bg


def _cell(min_ms: float, p50_ms: float, p95_ms: float) -> dict[str, object]:
    return {
        "min_ms": min_ms,
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
        "runs_ms": [min_ms, p50_ms, p50_ms, p50_ms, p95_ms],
    }


def _sample_suite() -> dict[str, object]:
    return {
        "schema": "wave93e-workstation-benchmarks-v3/1",
        "methodology_note": (
            "Native and Zero-C cells use full subprocess execution including "
            "~5 ms process spawn overhead."
        ),
        "kernels": [
            {
                "id": "sha256",
                "parity_ok": True,
                "parity_sha256": "a" * 64,
                "runtimes_verified": ["buildc_native", "zeroc_pe32", "node_wasm", "python_stdlib"],
                "buildc_native": _cell(4.8, 5.1, 5.9),
                "zeroc_pe32": _cell(3.9, 4.3, 4.8),
                "node_wasm": _cell(0.05, 0.06, 0.11),
                "python_stdlib": _cell(0.42, 0.44, 0.48),
            },
            {
                "id": "titan_1m",
                "parity_ok": True,
                "parity_sha256": "b" * 64,
                "runtimes_verified": ["buildc_native", "python_stdlib"],
                "buildc_native": _cell(12.0, 12.5, 13.5),
                "python_stdlib": _cell(350.0, 360.0, 380.0),
            },
        ],
        "summary": {"total_workloads": 2, "total_runtime_cells": 6},
    }


def test_suite_verifier_passes_clean_suite_and_seals_deterministically() -> None:
    suite = _sample_suite()
    rep = bg.verify_benchmark_suite(suite, baseline=suite, expected_workloads=2)
    assert rep.passed is True and rep.workloads_checked == 2 and rep.runtime_cells_checked == 6
    assert rep.sub_10ms_process_cells == 2 and rep.spawn_disclosure_ok is True
    assert len(rep.benchmark_attestation_sha256) == 64
    assert rep.benchmark_attestation_sha256 == bg.verify_benchmark_suite(suite).benchmark_attestation_sha256
    assert rep.to_dict()["passed"] is True


@pytest.mark.parametrize("bad_rt", bg.KNOWN_RUNTIMES)
def test_parity_check_catches_1hex_drift_on_every_runtime(bad_rt: str) -> None:
    digests = {rt: "a" * 64 for rt in bg.KNOWN_RUNTIMES}
    digests[bad_rt] = "f" + ("a" * 63)
    rep = bg.verify_runtime_digests("sha256", digests)
    assert rep.passed is False and rep.divergent_runtimes == (bad_rt,)
    assert any(f"RUNTIME_PARITY_DIVERGENCE:sha256:{bad_rt}" in r for r in rep.reasons)


def test_parity_check_catches_baseline_1hex_drift_and_bad_flags() -> None:
    base = _sample_suite()
    mut = copy.deepcopy(base)
    mut["kernels"][0]["parity_sha256"] = "0" + ("a" * 63)
    rep = bg.verify_benchmark_suite(mut, baseline=base)
    assert rep.passed is False and any("BASELINE_HASH_DRIFT:sha256:" in r for r in rep.reasons)

    bad = copy.deepcopy(base["kernels"][0])
    bad["parity_ok"] = False
    bad["runtimes_verified"] = ["buildc_native"]
    p_rep = bg.verify_kernel_parity(bad)
    assert p_rep.passed is False
    assert "PARITY_FLAG_FALSE:sha256" in p_rep.reasons
    assert "INSUFFICIENT_VERIFIED_RUNTIMES:sha256" in p_rep.reasons


def test_regression_gate_catches_inverted_p50_gt_p95_and_min_gt_p50() -> None:
    inv1 = bg.verify_cell_timings("k", "node_wasm", _cell(1.0, 5.0, 2.0))
    assert inv1.passed is False and any("TIMING_ORDER_INVARIANT_VIOLATED" in r for r in inv1.reasons)
    inv2 = bg.verify_cell_timings("k", "node_wasm", _cell(4.0, 2.0, 5.0))
    assert inv2.passed is False and any("TIMING_ORDER_INVARIANT_VIOLATED" in r for r in inv2.reasons)


@pytest.mark.parametrize("bad_val", [0.0, -1.5, float("nan"), float("inf"), True])
def test_regression_gate_rejects_non_positive_or_non_finite_timings(bad_val: object) -> None:
    cell = {"min_ms": bad_val, "p50_ms": 1.0, "p95_ms": 2.0, "runs_ms": [1.0] * 5}
    rep = bg.verify_cell_timings("k", "python_stdlib", cell)
    assert rep.passed is False and any("NON_POSITIVE_OR_NON_FINITE_TIMING" in r for r in rep.reasons)


def test_regression_gate_catches_variance_few_runs_and_sample_mismatch() -> None:
    noisy = bg.verify_cell_timings("k", "python_stdlib", _cell(0.5, 1.0, 15.0), max_p95_to_p50_ratio=10.0)
    assert noisy.passed is False and any("EXCESSIVE_VARIANCE_RATIO" in r for r in noisy.reasons)
    short = bg.verify_cell_timings("k", "python_stdlib", {"min_ms": 1.0, "p50_ms": 1.0, "p95_ms": 1.0, "runs_ms": [1.0, 1.0]})
    assert short.passed is False and any("INSUFFICIENT_TIMED_RUNS" in r for r in short.reasons)
    drift = bg.verify_cell_timings("k", "python_stdlib", {"min_ms": 0.1, "p50_ms": 1.0, "p95_ms": 1.5, "runs_ms": [1.0] * 5})
    assert drift.passed is False and any("MIN_SAMPLE_MISMATCH" in r for r in drift.reasons)


@pytest.mark.parametrize("proc_rt", ["buildc_native", "zeroc_pe32"])
def test_regression_gate_enforces_honest_spawn_disclosure_on_sub_10ms(proc_rt: str) -> None:
    ok_rep = bg.verify_cell_timings("sha256", proc_rt, _cell(4.0, 5.0, 6.0), has_spawn_disclosure=True)
    assert ok_rep.passed is True and ok_rep.sub_10ms_process_cell is True
    bad_rep = bg.verify_cell_timings("sha256", proc_rt, _cell(4.0, 5.0, 6.0), has_spawn_disclosure=False)
    assert bad_rep.passed is False and f"MISSING_SPAWN_FLOOR_DISCLOSURE:sha256:{proc_rt}" in bad_rep.reasons


def test_regression_gate_catches_over_2x_latency_regression() -> None:
    base = _sample_suite()
    slow = copy.deepcopy(base)
    slow["kernels"][1]["buildc_native"] = _cell(25.0, 26.0, 28.0)  # 26.0 / 12.5 = 2.08x > 2.0x
    rep = bg.verify_benchmark_suite(slow, baseline=base, max_regression_ratio=2.0)
    assert rep.passed is False and any("LATENCY_REGRESSION:titan_1m:buildc_native:" in r for r in rep.reasons)
    ok_slow = copy.deepcopy(base)
    ok_slow["kernels"][1]["buildc_native"] = _cell(17.0, 18.0, 19.0)  # 1.44x <= 2.0x
    assert bg.verify_benchmark_suite(ok_slow, baseline=base, max_regression_ratio=2.0).passed is True


def test_suite_file_loader_and_missing_disclosure_fail_closed(tmp_path: Path) -> None:
    assert "MISSING_SUITE_FILE" in bg.verify_benchmark_suite_file(tmp_path / "no.json").reasons
    suite_p = tmp_path / "suite.json"
    bad = _sample_suite()
    bad["methodology_note"] = "Fast timings only."
    suite_p.write_text(json.dumps(bad), encoding="utf-8")
    rep = bg.verify_benchmark_suite_file(suite_p)
    assert rep.passed is False and rep.spawn_disclosure_ok is False
    assert any("MISSING_SPAWN_FLOOR_DISCLOSURE:" in r for r in rep.reasons)


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("Subprocess execution includes ~5 ms spawn overhead", True),
        ("Wall-clock process overhead disclosed", True),
        ("Fast timings only", False),
        ("", False),
    ],
)
def test_spawn_disclosure_detector(note: str, expected: bool) -> None:
    assert bg.has_honest_spawn_disclosure(note) is expected


@pytest.mark.parametrize(("mult", "should_pass"), [(0.9, True), (1.5, True), (2.0, True), (2.01, False), (3.5, False)])
def test_regression_ratio_boundary_at_2x(mult: float, should_pass: bool) -> None:
    p50 = round(10.0 * mult, 4)
    rep = bg.verify_cell_timings("k", "node_wasm", _cell(p50 * 0.9, p50, p50 * 1.1), baseline_p50_ms=10.0)
    assert rep.passed is should_pass


def test_package_hygiene_loc_spdx_stdlib_and_scope_limits() -> None:
    root = Path(__file__).resolve().parents[1]
    pkg_files = sorted((root / "harness" / "benchmark_gate").glob("*.py"))
    assert len(pkg_files) == 4
    assert set(bg.HONEST_SCOPE_LIMITS) == {"parity_check", "regression_gate", "suite_verifier"}
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
