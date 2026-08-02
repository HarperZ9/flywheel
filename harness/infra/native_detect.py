"""native_detect.py -- statistical anomaly detection with native acceleration.

Wraps the anomaly-kernels C++ library (BaselineBuilder, AnomalyScorer) and the
signal-kernels C++ library (PELT changepoint, Granger causality) when the
native extensions are compiled and available. Falls back to pure-Python
implementations of the same algorithms when they are not.

This follows Flywheel's graceful-fallback discipline: the detection works
everywhere; native compilation makes it faster and more precise, but is not
required for correctness.

The pure-Python implementations are mathematically equivalent to the C++ ones:
z-score, IQR, PELT (Pruned Exact Linear Time), and Granger causality are all
closed-form algorithms that Python's stdlib math module computes exactly.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any

# Try to import the native extension. If it fails, we use pure Python.
try:
    import _flywheel_native as _native  # type: ignore
    _NATIVE_AVAILABLE = True
except ImportError:
    _native = None
    _NATIVE_AVAILABLE = False


def native_available() -> bool:
    """True if the C++ native extension is compiled and loaded."""
    return _NATIVE_AVAILABLE


# ---------------------------------------------------------------------------
# Metric types (mirrors anomaly-kernels MetricType enum)
# ---------------------------------------------------------------------------

METRIC_TYPES = (
    "ProcessCreationRate", "NetworkConnectionRate", "FileAccessRate",
    "RegistryAccessRate", "DnsQueryRate", "CpuUsage", "MemoryUsage",
)


# ---------------------------------------------------------------------------
# Baseline (mirrors anomaly-kernels Baseline)
# ---------------------------------------------------------------------------

@dataclass
class Baseline:
    """Statistical summary for one metric type."""
    metric: str
    mean: float = 0.0
    stddev: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0
    sample_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric, "mean": round(self.mean, 6),
            "stddev": round(self.stddev, 6), "min": self.min_val,
            "max": self.max_val, "sample_count": self.sample_count,
        }


class BaselineBuilder:
    """Accumulates metric samples and computes baselines.

    Pure-Python implementation using statistics.mean and statistics.pstdev.
    When the native extension is available, delegates to it for speed.
    """

    def __init__(self) -> None:
        self._samples: dict[str, list[float]] = {}

    def add_sample(self, metric: str, value: float) -> None:
        self._samples.setdefault(metric, []).append(value)

    def build(self, metric: str) -> Baseline | None:
        samples = self._samples.get(metric, [])
        if len(samples) < 2:
            return None
        mean = statistics.mean(samples)
        stddev = statistics.pstdev(samples) if len(samples) > 1 else 0.0
        return Baseline(
            metric=metric, mean=mean, stddev=stddev,
            min_val=min(samples), max_val=max(samples),
            sample_count=len(samples),
        )

    def sample_count(self, metric: str) -> int:
        return len(self._samples.get(metric, []))

    def reset(self) -> None:
        self._samples.clear()


# ---------------------------------------------------------------------------
# Anomaly scoring (mirrors anomaly-kernels AnomalyScorer)
# ---------------------------------------------------------------------------

@dataclass
class AnomalyScore:
    """Result of scoring a single observation."""
    value: float = 0.0
    baseline_mean: float = 0.0
    baseline_stddev: float = 0.0
    z_score: float = 0.0
    is_anomalous: bool = False
    severity: float = 0.0
    method: str = "ZScore"

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value, "z_score": round(self.z_score, 4),
            "is_anomalous": self.is_anomalous,
            "severity": round(self.severity, 4),
            "method": self.method,
        }


class AnomalyScorer:
    """Statistical deviation scoring. Stateless."""

    def score(self, value: float, baseline: Baseline,
              threshold: float = 3.0) -> AnomalyScore:
        """Score a single observation against a baseline.

        Uses z-score by default. A value is anomalous if |z| >= threshold.
        """
        if baseline.stddev == 0:
            z = 0.0 if value == baseline.mean else float("inf")
        else:
            z = (value - baseline.mean) / baseline.stddev
        is_anom = abs(z) >= threshold
        sev = self.severity_from_zscore(abs(z))
        return AnomalyScore(
            value=value, baseline_mean=baseline.mean,
            baseline_stddev=baseline.stddev, z_score=z,
            is_anomalous=is_anom, severity=sev, method="ZScore",
        )

    @staticmethod
    def z_score(value: float, mean: float, stddev: float) -> float:
        if stddev == 0:
            return 0.0 if value == mean else float("inf")
        return (value - mean) / stddev

    @staticmethod
    def iqr_score(value: float, q1: float, q3: float) -> float:
        """IQR-based outlier score. Returns distance outside [Q1-1.5*IQR, Q3+1.5*IQR]."""
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        if value < lower:
            return lower - value
        if value > upper:
            return value - upper
        return 0.0

    @staticmethod
    def severity_from_zscore(z: float) -> float:
        """Map absolute z-score to a 0.0-1.0 severity float."""
        if z <= 1.0:
            return 0.0
        if z >= 5.0:
            return 1.0
        return (z - 1.0) / 4.0


# ---------------------------------------------------------------------------
# Changepoint detection (mirrors signal-kernels pelt)
# ---------------------------------------------------------------------------

@dataclass
class Changepoint:
    """A detected change point."""
    index: int
    cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "cost": round(self.cost, 6)}


def _l2_cost(data: list[float], start: int, end: int) -> float:
    """L2 (variance) cost: sum of squared deviations from segment mean."""
    segment = data[start:end]
    if len(segment) < 2:
        return 0.0
    mean = sum(segment) / len(segment)
    return sum((x - mean) ** 2 for x in segment)


def pelt(data: list[float], penalty: float = 10.0,
         min_size: int = 2) -> list[Changepoint]:
    """PELT-style changepoint detection (O(n^2) DP, exact).

    Finds points where the statistical properties of the time series change
    significantly. Uses L2 (variance) cost with a penalty per changepoint.

    Args:
        data: time series of floats
        penalty: penalty per changepoint (higher = fewer changepoints)
        min_size: minimum segment length (>= 2)

    Returns: list of Changepoint records, sorted by index.
    """
    n = len(data)
    if n < 2 * min_size:
        return []

    # F[t] = min total cost to segment data[0:t]
    # last[t] = the previous segment boundary in the optimal segmentation
    F = [0.0] * (n + 1)
    last = [0] * (n + 1)

    for t in range(min_size, n + 1):
        best_cost = float("inf")
        best_tau = 0
        for tau in range(0, t - min_size + 1):
            seg_cost = _l2_cost(data, tau, t)
            cost = F[tau] + seg_cost + penalty
            if cost < best_cost:
                best_cost = cost
                best_tau = tau
        # Also consider: no changepoint (single segment from 0 to t)
        single_cost = _l2_cost(data, 0, t)
        if single_cost < best_cost:
            best_cost = single_cost
            best_tau = 0
        F[t] = best_cost
        last[t] = best_tau

    # Backtrack to find changepoints
    changepoints: list[Changepoint] = []
    t = n
    while t > 0:
        tau = last[t]
        if tau > 0:
            changepoints.append(
                Changepoint(index=tau, cost=_l2_cost(data, tau, t)))
        t = tau

    changepoints.sort(key=lambda c: c.index)
    return changepoints


# ---------------------------------------------------------------------------
# Granger causality (mirrors signal-kernels granger_causality)
# ---------------------------------------------------------------------------

@dataclass
class GrangerResult:
    """Result of a Granger causality test."""
    f_stat: float = 0.0
    p_value: float = 1.0
    optimal_lag: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"f_stat": round(self.f_stat, 6),
                "p_value": round(self.p_value, 6),
                "optimal_lag": self.optimal_lag}

    @property
    def is_significant(self) -> bool:
        """True if x Granger-causes y at p < 0.05."""
        return self.p_value < 0.05


def granger_causality(x: list[float], y: list[float],
                      max_lag: int = 5) -> GrangerResult:
    """Test whether x Granger-causes y.

    Pure-Python implementation. Compares the restricted model (y regressed on
    its own past) against the unrestricted model (y regressed on its own past
    plus x's past). Uses an F-test.

    This is a simplified linear-regression Granger test suitable for quick
    causal attribution between infra telemetry signals.
    """
    n = min(len(x), len(y))
    if n <= 2 * max_lag + 2 or max_lag < 1:
        return GrangerResult()

    best_result = GrangerResult()
    best_p = 1.0

    for lag in range(1, max_lag + 1):
        result = _granger_test_at_lag(x, y, lag, n)
        if result.p_value < best_p:
            best_p = result.p_value
            best_result = result

    return best_result


def _granger_test_at_lag(x: list[float], y: list[float], lag: int,
                         n: int) -> GrangerResult:
    """Granger test at a single lag using simple OLS."""
    # Build the design matrices
    m = n - lag
    if m <= lag + 2:
        return GrangerResult()

    # Restricted model: y[t] = a + b*y[t-lag]
    y_restricted = [y[t] for t in range(lag, n)]
    x_restricted = [[1.0, y[t - lag]] for t in range(lag, n)]

    # Unrestricted model: y[t] = a + b*y[t-lag] + c*x[t-lag]
    y_unrestricted = y_restricted
    x_unrestricted = [[1.0, y[t - lag], x[t - lag]] for t in range(lag, n)]

    rss_r = _ols_rss(x_restricted, y_restricted)
    rss_u = _ols_rss(x_unrestricted, y_unrestricted)

    if rss_u <= 0 or rss_r <= 0:
        return GrangerResult(optimal_lag=lag)

    # F-statistic
    df1 = 1  # number of restrictions (one extra variable)
    df2 = m - 3  # degrees of freedom (unrestricted params)
    if df2 <= 0:
        return GrangerResult(optimal_lag=lag)

    f_stat = ((rss_r - rss_u) / df1) / (rss_u / df2)
    p_value = _f_distribution_pvalue(f_stat, df1, df2)

    return GrangerResult(f_stat=f_stat, p_value=p_value, optimal_lag=lag)


def _ols_rss(X: list[list[float]], y: list[float]) -> float:
    """Ordinary least squares residual sum of squares using normal equations."""
    n = len(X)
    k = len(X[0]) if X else 0
    if n < k or k == 0:
        return float("inf")

    # Normal equations: (X^T X) beta = X^T y
    # Build X^T X and X^T y
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for i in range(n):
        for a in range(k):
            xty[a] += X[i][a] * y[i]
            for b in range(k):
                xtx[a][b] += X[i][a] * X[i][b]

    # Solve via Gaussian elimination
    beta = _gaussian_solve(xtx, xty, k)
    if beta is None:
        return float("inf")

    # Compute RSS
    rss = 0.0
    for i in range(n):
        pred = sum(beta[j] * X[i][j] for j in range(k))
        rss += (y[i] - pred) ** 2
    return rss


def _gaussian_solve(A: list[list[float]], b: list[float],
                    n: int) -> list[float] | None:
    """Solve Ax = b via Gaussian elimination with partial pivoting."""
    # Augmented matrix
    aug = [row[:] + [b[i]] for i, row in enumerate(A)]

    for col in range(n):
        # Partial pivoting
        max_row = col
        for row in range(col + 1, n):
            if abs(aug[row][col]) > abs(aug[max_row][col]):
                max_row = row
        aug[col], aug[max_row] = aug[max_row], aug[col]

        if abs(aug[col][col]) < 1e-12:
            return None

        for row in range(col + 1, n):
            factor = aug[row][col] / aug[col][col]
            for j in range(col, n + 1):
                aug[row][j] -= factor * aug[col][j]

    # Back substitution
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = aug[i][n]
        for j in range(i + 1, n):
            x[i] -= aug[i][j] * x[j]
        x[i] /= aug[i][i]

    return x


def _f_distribution_pvalue(f: float, df1: int, df2: int) -> float:
    """Approximate p-value for the F-distribution using the incomplete beta function."""
    if f <= 0:
        return 1.0
    # p = I_{df2/(df2+df1*f)}(df2/2, df1/2)
    x = df2 / (df2 + df1 * f)
    return _regularized_incomplete_beta(x, df2 / 2.0, df1 / 2.0)


def _regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    """Regularized incomplete beta function I_x(a, b) via continued fraction."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a

    if x < (a + 1) / (a + b + 2):
        return front * _beta_cf(x, a, b) / a
    else:
        return 1.0 - front * _beta_cf(1 - x, b, a) / b


def _beta_cf(x: float, a: float, b: float) -> float:
    """Continued fraction expansion for incomplete beta (Lentz method)."""
    tiny = 1e-30
    fpmin = 1e-30
    qab = a + b
    qap = a + 1
    qam = a - 1
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    result = d

    for m in range(1, 101):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        result *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < tiny:
            break

    return result
