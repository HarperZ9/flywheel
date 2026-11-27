# SPDX-License-Identifier: MIT
"""Statistical timing, spawn-floor disclosure, and latency regression gate.

Enforces finite positive timings, min <= p50 <= p95 order invariants, sample
consistency, bounded variance, honest process-spawn disclosure for sub-10ms
subprocess cells, and latency regression ceilings against baseline records.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

HONEST_SCOPE_LIMIT = (
    "Validates recorded timing summary statistics, sample-array consistency, "
    "bounded p95/p50 spread, honest subprocess spawn-floor disclosures, and "
    "baseline regression ratios. Does not control host OS scheduling jitter "
    "or CPU frequency scaling during benchmark execution."
)

PROCESS_LAUNCHED_RUNTIMES: frozenset[str] = frozenset({"buildc_native", "zeroc_pe32"})
SPAWN_FLOOR_THRESHOLD_MS = 10.0


@dataclass(frozen=True)
class CellTimingReport:
    """Fail-closed timing and regression audit result for one runtime cell."""

    passed: bool
    kernel_id: str
    runtime: str
    min_ms: float
    p50_ms: float
    p95_ms: float
    sample_count: int
    sub_10ms_process_cell: bool
    regression_ratio: float | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize timing report into a JSON-compatible dictionary."""
        return {
            "passed": self.passed,
            "kernel_id": self.kernel_id,
            "runtime": self.runtime,
            "min_ms": self.min_ms,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "sample_count": self.sample_count,
            "sub_10ms_process_cell": self.sub_10ms_process_cell,
            "regression_ratio": self.regression_ratio,
            "reasons": list(self.reasons),
        }


def _is_pos_finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def has_honest_spawn_disclosure(note: object) -> bool:
    """Check that methodology text explicitly discloses subprocess spawn cost."""
    if not isinstance(note, str):
        return False
    low = note.lower()
    has_proc = ("subprocess" in low) or ("process" in low)
    has_spawn = ("spawn" in low) or ("overhead" in low)
    return has_proc and has_spawn


def _check_samples(
    kernel_id: str,
    runtime: str,
    runs: object,
    min_runs: int,
    valid_stats: bool,
    stats: tuple[float, float, float],
    reasons: list[str],
) -> int:
    if not isinstance(runs, list) or len(runs) < min_runs:
        reasons.append(f"INSUFFICIENT_TIMED_RUNS:{kernel_id}:{runtime}")
        return 0
    if not all(_is_pos_finite(x) for x in runs):
        reasons.append(f"INVALID_RUN_SAMPLE:{kernel_id}:{runtime}")
    elif valid_stats:
        min_ms, p50_ms, p95_ms = stats
        vals = [float(x) for x in runs]
        lo, hi = min(vals), max(vals)
        if abs(lo - min_ms) > 1e-3:
            reasons.append(f"MIN_SAMPLE_MISMATCH:{kernel_id}:{runtime}")
        if not (lo - 1e-3 <= p50_ms <= hi + 1e-3) or not (lo - 1e-3 <= p95_ms <= hi + 1e-3):
            reasons.append(f"PERCENTILE_OUT_OF_SAMPLE_RANGE:{kernel_id}:{runtime}")
    return len(runs)


def _check_regression(
    kernel_id: str,
    runtime: str,
    baseline_p50_ms: float | None,
    p50_ms: float,
    valid_stats: bool,
    max_regression_ratio: float,
    reasons: list[str],
) -> float | None:
    if baseline_p50_ms is None:
        return None
    if not _is_pos_finite(baseline_p50_ms):
        reasons.append(f"INVALID_BASELINE_P50:{kernel_id}:{runtime}")
        return None
    if not valid_stats:
        return None
    ratio = round(p50_ms / float(baseline_p50_ms), 4)
    if ratio > max_regression_ratio:
        reasons.append(f"LATENCY_REGRESSION:{kernel_id}:{runtime}:{ratio:.2f}x>{max_regression_ratio:.2f}x")
    return ratio


def verify_cell_timings(
    kernel_id: str,
    runtime: str,
    cell: Mapping[str, object],
    *,
    baseline_p50_ms: float | None = None,
    max_regression_ratio: float = 2.0,
    max_p95_to_p50_ratio: float = 10.0,
    min_runs: int = 5,
    has_spawn_disclosure: bool = True,
) -> CellTimingReport:
    """Verify timing invariants and baseline regression bounds for one cell."""
    if not isinstance(cell, Mapping):
        return CellTimingReport(False, kernel_id, runtime, 0.0, 0.0, 0.0, 0, False, None, (f"INVALID_CELL:{kernel_id}:{runtime}",))
    reasons: list[str] = []
    raw_min, raw_p50, raw_p95 = cell.get("min_ms"), cell.get("p50_ms"), cell.get("p95_ms")
    valid_stats = _is_pos_finite(raw_min) and _is_pos_finite(raw_p50) and _is_pos_finite(raw_p95)
    min_ms = float(raw_min) if _is_pos_finite(raw_min) else 0.0
    p50_ms = float(raw_p50) if _is_pos_finite(raw_p50) else 0.0
    p95_ms = float(raw_p95) if _is_pos_finite(raw_p95) else 0.0
    if not valid_stats:
        reasons.append(f"NON_POSITIVE_OR_NON_FINITE_TIMING:{kernel_id}:{runtime}")
    else:
        if not (min_ms <= p50_ms <= p95_ms):
            reasons.append(f"TIMING_ORDER_INVARIANT_VIOLATED:{kernel_id}:{runtime}:{min_ms}/{p50_ms}/{p95_ms}")
        if p50_ms > 0.0 and (p95_ms / p50_ms) > max_p95_to_p50_ratio:
            reasons.append(f"EXCESSIVE_VARIANCE_RATIO:{kernel_id}:{runtime}:{p95_ms / p50_ms:.2f}")
    sample_count = _check_samples(kernel_id, runtime, cell.get("runs_ms"), min_runs, valid_stats, (min_ms, p50_ms, p95_ms), reasons)
    sub_10ms = valid_stats and runtime in PROCESS_LAUNCHED_RUNTIMES and p50_ms < SPAWN_FLOOR_THRESHOLD_MS
    if sub_10ms and not has_spawn_disclosure:
        reasons.append(f"MISSING_SPAWN_FLOOR_DISCLOSURE:{kernel_id}:{runtime}")
    reg_ratio = _check_regression(kernel_id, runtime, baseline_p50_ms, p50_ms, valid_stats, max_regression_ratio, reasons)
    return CellTimingReport(not reasons, kernel_id, runtime, min_ms, p50_ms, p95_ms, sample_count, sub_10ms, reg_ratio, tuple(reasons))
