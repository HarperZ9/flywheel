# SPDX-License-Identifier: MIT
"""Extreme-value tail-risk metrics (p99, CVaR_99, and max excursion ratio).

Computes exact order-statistic quantiles, Conditional Value at Risk (Expected
Shortfall at the 99th percentile), maximum excursion ratio relative to median,
and fail-closed detection of NaN and Inf sample propagation.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

HONEST_SCOPE_LIMIT = (
    "Computes empirical order-statistic quantiles (p50, p95, p99), empirical "
    "CVaR_99 (mean of samples at or above p99), max excursion ratio, and "
    "non-finite sample counts over finite sample vectors. Empirical tail "
    "estimates depend on sample count and do not fit parametric EVT models."
)


@dataclass(frozen=True)
class TailRiskMetrics:
    """Distributional tail-risk summary over a sequence of numeric outcomes."""

    sample_count: int
    finite_count: int
    non_finite_count: int
    has_nan: bool
    has_inf: bool
    min_val: float
    p50: float
    p95: float
    p99: float
    cvar_99: float
    max_val: float
    max_excursion_ratio: float

    def to_dict(self) -> dict[str, object]:
        """Serialize tail metrics into a deterministic JSON-compatible dict."""
        return {
            "sample_count": self.sample_count,
            "finite_count": self.finite_count,
            "non_finite_count": self.non_finite_count,
            "has_nan": self.has_nan,
            "has_inf": self.has_inf,
            "min_val": self.min_val,
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
            "cvar_99": self.cvar_99,
            "max_val": self.max_val,
            "max_excursion_ratio": self.max_excursion_ratio,
        }


def quantile_sorted(sorted_vals: Sequence[float], q: float) -> float:
    """Compute exact linear-interpolated quantile over a non-empty sorted list."""
    if not sorted_vals:
        raise ValueError("sorted_vals must be non-empty")
    if not (0.0 <= q <= 1.0):
        raise ValueError("q must lie in [0.0, 1.0]")
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_vals[lo])
    frac = pos - lo
    return float(sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo]))


def _partition_samples(samples: Sequence[object]) -> tuple[list[float], int, bool, bool]:
    finite: list[float] = []
    non_finite, has_nan, has_inf = 0, False, False
    for item in samples:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            non_finite += 1
            has_nan = True
            continue
        val = float(item)
        if math.isnan(val):
            non_finite += 1
            has_nan = True
        elif math.isinf(val):
            non_finite += 1
            has_inf = True
        else:
            finite.append(val)
    return finite, non_finite, has_nan, has_inf


def compute_tail_metrics(
    samples: Sequence[object],
    *,
    alpha: float = 0.99,
    median_floor: float = 1e-9,
) -> TailRiskMetrics:
    """Compute p50, p95, p99, CVaR_99, max excursion ratio, and NaN/Inf counts."""
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must lie strictly inside (0.0, 1.0)")
    if not samples:
        raise ValueError("samples must be non-empty")
    finite, non_finite, has_nan, has_inf = _partition_samples(samples)
    if not finite:
        return TailRiskMetrics(len(samples), 0, non_finite, has_nan, has_inf, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    ordered = sorted(finite)
    p50, p95 = quantile_sorted(ordered, 0.50), quantile_sorted(ordered, 0.95)
    p_alpha = quantile_sorted(ordered, alpha)
    tail = [v for v in ordered if v >= p_alpha]
    cvar = sum(tail) / len(tail) if tail else ordered[-1]
    max_val = ordered[-1]
    excursion = abs(max_val) / max(abs(p50), median_floor)
    return TailRiskMetrics(
        len(samples), len(finite), non_finite, has_nan, has_inf,
        round(ordered[0], 9), round(p50, 9), round(p95, 9), round(p_alpha, 9),
        round(cvar, 9), round(max_val, 9), round(excursion, 6),
    )
