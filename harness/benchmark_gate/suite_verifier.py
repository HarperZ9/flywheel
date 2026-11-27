# SPDX-License-Identifier: MIT
"""Cross-runtime benchmark suite verifier and deterministic attestation sealer.

Audits serialized benchmark suite JSON artifacts (such as Benchmark Suite V3)
across all workloads and runtime cells for output digest parity, statistical
timing invariants, honest process-spawn disclosure, and baseline regression
ceilings, sealing a deterministic benchmark_attestation_sha256.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .parity_check import verify_kernel_parity
from .regression_gate import has_honest_spawn_disclosure, verify_cell_timings

HONEST_SCOPE_LIMIT = (
    "Audits serialized cross-runtime benchmark JSON files for output digest "
    "parity, statistical timing invariants, subprocess spawn disclosures, and "
    "optional baseline regression limits. Does not compile or execute the "
    "benchmarked kernels."
)


@dataclass(frozen=True)
class SuiteVerificationReport:
    """Fail-closed attestation summary for a cross-runtime benchmark suite."""

    passed: bool
    schema: str
    workloads_checked: int
    runtime_cells_checked: int
    sub_10ms_process_cells: int
    spawn_disclosure_ok: bool
    reasons: tuple[str, ...]
    benchmark_attestation_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Serialize suite verification summary into a JSON-compatible dict."""
        return {
            "passed": self.passed,
            "schema": self.schema,
            "workloads_checked": self.workloads_checked,
            "runtime_cells_checked": self.runtime_cells_checked,
            "sub_10ms_process_cells": self.sub_10ms_process_cells,
            "spawn_disclosure_ok": self.spawn_disclosure_ok,
            "reasons": list(self.reasons),
            "benchmark_attestation_sha256": self.benchmark_attestation_sha256,
        }


def _seal_suite(
    schema: str,
    kernel_summaries: Sequence[dict[str, object]],
    passed: bool,
    reasons: Sequence[str],
) -> str:
    payload = {
        "schema": schema,
        "passed": passed,
        "reasons": list(reasons),
        "kernels": list(kernel_summaries),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _index_baseline(baseline: Mapping[str, object] | None) -> dict[str, Mapping[str, object]]:
    if not isinstance(baseline, Mapping):
        return {}
    kernels = baseline.get("kernels")
    if not isinstance(kernels, list):
        return {}
    indexed: dict[str, Mapping[str, object]] = {}
    for item in kernels:
        if isinstance(item, Mapping) and isinstance(item.get("id"), str):
            indexed[str(item["id"])] = item
    return indexed


def _verify_kernel_cells(
    kid: str,
    kernel: Mapping[str, object],
    base_k: Mapping[str, object] | None,
    *,
    spawn_ok: bool,
    max_regression_ratio: float,
    max_p95_to_p50_ratio: float,
    min_runs: int,
    reasons: list[str],
) -> tuple[dict[str, object], int, int]:
    rts = kernel.get("runtimes_verified") if isinstance(kernel.get("runtimes_verified"), list) else []
    cell_digests: dict[str, object] = {}
    cells, sub_10ms = 0, 0
    for rt_obj in rts:
        rt = str(rt_obj)
        cell = kernel.get(rt)
        if not isinstance(cell, Mapping):
            continue
        cells += 1
        base_p50: float | None = None
        if base_k and isinstance(base_k.get(rt), Mapping):
            raw_bp = base_k[rt].get("p50_ms")
            if isinstance(raw_bp, (int, float)) and not isinstance(raw_bp, bool):
                base_p50 = float(raw_bp)
        t_rep = verify_cell_timings(
            kid, rt, cell, baseline_p50_ms=base_p50, max_regression_ratio=max_regression_ratio,
            max_p95_to_p50_ratio=max_p95_to_p50_ratio, min_runs=min_runs, has_spawn_disclosure=spawn_ok,
        )
        if t_rep.sub_10ms_process_cell:
            sub_10ms += 1
        if not t_rep.passed:
            reasons.extend(t_rep.reasons)
        cell_digests[rt] = {"min_ms": t_rep.min_ms, "p50_ms": t_rep.p50_ms, "p95_ms": t_rep.p95_ms}
    return cell_digests, cells, sub_10ms


def _check_summary_counts(suite: Mapping[str, object], kernel_count: int, total_cells: int, reasons: list[str]) -> None:
    summary = suite.get("summary")
    if isinstance(summary, Mapping):
        if summary.get("total_workloads") is not None and summary.get("total_workloads") != kernel_count:
            reasons.append("SUMMARY_WORKLOAD_COUNT_MISMATCH")
        if summary.get("total_runtime_cells") is not None and summary.get("total_runtime_cells") != total_cells:
            reasons.append("SUMMARY_CELL_COUNT_MISMATCH")


def _verify_one_kernel(
    idx: int,
    k: object,
    seen_ids: set[str],
    baseline_map: dict[str, Mapping[str, object]],
    *,
    spawn_ok: bool,
    max_regression_ratio: float,
    max_p95_to_p50_ratio: float,
    min_runs: int,
    reasons: list[str],
) -> tuple[dict[str, object] | None, int, int]:
    if not isinstance(k, Mapping):
        reasons.append(f"INVALID_KERNEL_ENTRY:{idx}")
        return None, 0, 0
    kid = str(k.get("id", f"kernel_{idx}"))
    if kid in seen_ids:
        reasons.append(f"DUPLICATE_KERNEL_ID:{kid}")
    seen_ids.add(kid)
    base_k = baseline_map.get(kid)
    exp_sha = str(base_k["parity_sha256"]) if base_k and isinstance(base_k.get("parity_sha256"), str) else None
    p_rep = verify_kernel_parity(k, expected_sha256=exp_sha)
    if not p_rep.passed:
        reasons.extend(p_rep.reasons)
    cd, c_cnt, s_cnt = _verify_kernel_cells(
        kid, k, base_k, spawn_ok=spawn_ok, max_regression_ratio=max_regression_ratio,
        max_p95_to_p50_ratio=max_p95_to_p50_ratio, min_runs=min_runs, reasons=reasons,
    )
    return {"id": kid, "parity_sha256": p_rep.consensus_sha256, "cells": cd}, c_cnt, s_cnt


def verify_benchmark_suite(
    suite: Mapping[str, object],
    *,
    baseline: Mapping[str, object] | None = None,
    max_regression_ratio: float = 2.0,
    max_p95_to_p50_ratio: float = 10.0,
    min_runs: int = 5,
    expected_workloads: int | None = None,
) -> SuiteVerificationReport:
    """Verify a cross-runtime benchmark suite mapping fail-closed."""
    if not isinstance(suite, Mapping):
        r = ("INVALID_SUITE_OBJECT",)
        return SuiteVerificationReport(False, "", 0, 0, 0, False, r, _seal_suite("", (), False, r))
    reasons: list[str] = []
    schema = str(suite.get("schema", ""))
    if not schema:
        reasons.append("MISSING_SUITE_SCHEMA")
    kernels = suite.get("kernels")
    if not isinstance(kernels, list) or not kernels:
        reasons.append("EMPTY_KERNEL_LIST")
        return SuiteVerificationReport(False, schema, 0, 0, 0, False, tuple(reasons), _seal_suite(schema, (), False, reasons))
    if expected_workloads is not None and len(kernels) != expected_workloads:
        reasons.append(f"WORKLOAD_COUNT_MISMATCH:{len(kernels)}!={expected_workloads}")
    spawn_ok = has_honest_spawn_disclosure(suite.get("methodology_note"))
    baseline_map = _index_baseline(baseline)
    seen_ids: set[str] = set()
    summaries: list[dict[str, object]] = []
    total_cells = sub_10ms_cells = 0
    for idx, k in enumerate(kernels):
        item, c_cnt, s_cnt = _verify_one_kernel(
            idx, k, seen_ids, baseline_map, spawn_ok=spawn_ok,
            max_regression_ratio=max_regression_ratio,
            max_p95_to_p50_ratio=max_p95_to_p50_ratio, min_runs=min_runs, reasons=reasons,
        )
        total_cells += c_cnt
        sub_10ms_cells += s_cnt
        if item is not None:
            summaries.append(item)
    _check_summary_counts(suite, len(kernels), total_cells, reasons)
    unique = tuple(dict.fromkeys(reasons))
    passed = not unique
    return SuiteVerificationReport(passed, schema, len(kernels), total_cells, sub_10ms_cells, spawn_ok, unique, _seal_suite(schema, summaries, passed, unique))


def verify_benchmark_suite_file(
    suite_path: Path,
    *,
    baseline_path: Path | None = None,
    max_regression_ratio: float = 2.0,
    max_p95_to_p50_ratio: float = 10.0,
    min_runs: int = 5,
    expected_workloads: int | None = None,
) -> SuiteVerificationReport:
    """Load suite JSON (and optional baseline JSON) from disk and verify."""
    if not suite_path.is_file():
        reasons = ("MISSING_SUITE_FILE",)
        return SuiteVerificationReport(False, "", 0, 0, 0, False, reasons, _seal_suite("", (), False, reasons))
    try:
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        reasons = ("INVALID_SUITE_JSON",)
        return SuiteVerificationReport(False, "", 0, 0, 0, False, reasons, _seal_suite("", (), False, reasons))

    baseline: Mapping[str, object] | None = None
    if baseline_path is not None:
        if not baseline_path.is_file():
            reasons = ("MISSING_BASELINE_FILE",)
            return SuiteVerificationReport(False, "", 0, 0, 0, False, reasons, _seal_suite("", (), False, reasons))
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            reasons = ("INVALID_BASELINE_JSON",)
            return SuiteVerificationReport(False, "", 0, 0, 0, False, reasons, _seal_suite("", (), False, reasons))

    return verify_benchmark_suite(
        suite,
        baseline=baseline,
        max_regression_ratio=max_regression_ratio,
        max_p95_to_p50_ratio=max_p95_to_p50_ratio,
        min_runs=min_runs,
        expected_workloads=expected_workloads,
    )
