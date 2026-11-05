"""d2 on measured series: AR fits, error bars, detrending, sliding windows and the early-warning trend.

Early-warning use reads d2 in windows before an event. A two-sided smoother lets the event itself leak into the
residuals before it, which can fake a warning, so `sliding` detrends with a past-only (causal) Gaussian kernel by
default. The two-sided kernel stays available (`detrend="gaussian"`) for whole-series summaries.
"""
from __future__ import annotations

import math

from .core import LN2, d_beta, is_stationary, levinson, solve

SCOPE_D2 = ["KL_RATE_TO_NEAREST_CRITICAL_AR_SAME_ORDER", "GAUSSIAN_AR_FIT_OF_SERIES"]


def _segments(x):
    if isinstance(x, (list, tuple)) and x and isinstance(x[0], (list, tuple)):
        return [[float(v) for v in s] for s in x]
    return [[float(v) for v in x]]


def zscore(x):
    segs = _segments(x)
    allx = [v for s in segs for v in s]
    mu = sum(allx) / len(allx)
    sd = math.sqrt(sum((v - mu) ** 2 for v in allx) / len(allx))
    if not sd > 0:
        raise ValueError("series has zero variance")
    return [[(v - mu) / sd for v in s] for s in segs]


def sample_acov(segs, maxlag, biased=True):
    """Pooled autocovariance. biased=True divides by the sample count (positive definite, so the Yule-Walker fit
    is always stationary); biased=False divides by the pair count, the authors' toolkit convention."""
    num = [0.0] * (maxlag + 1)
    pairs = [0] * (maxlag + 1)
    N = 0
    for s in segs:
        N += len(s)
        for h in range(min(maxlag, len(s) - 1) + 1):
            num[h] += sum(s[i] * s[i + h] for i in range(len(s) - h))
            pairs[h] += len(s) - h
    return [num[h] / (N if biased else max(pairs[h], 1)) for h in range(maxlag + 1)]


def fit_yw(x, order, biased=True):
    """Yule-Walker AR(order) on the z-scored series. Returns (phi, sigma2)."""
    g = sample_acov(zscore(x), order, biased)
    return levinson([v / g[0] for v in g], order)


def fit_ols(x, order):
    """Conditional least squares (the MLE of the paper's SI 2.5 without pre-sample padding).

    Returns (phi, sigma2, cov_phi) with cov_phi = sigma2 (X'X)^-1."""
    XtX = [[0.0] * order for _ in range(order)]
    Xty = [0.0] * order
    rows = []
    for s in zscore(x):
        for t in range(order, len(s)):
            r = [s[t - j] for j in range(1, order + 1)]
            rows.append((r, s[t]))
            for i in range(order):
                Xty[i] += r[i] * s[t]
                for j in range(order):
                    XtX[i][j] += r[i] * r[j]
    phi = solve(XtX, Xty)
    s2 = sum((y - sum(p * v for p, v in zip(phi, r))) ** 2 for r, y in rows) / len(rows)
    inv_cols = [solve(XtX, [1.0 if i == j else 0.0 for i in range(order)]) for j in range(order)]
    cov = [[s2 * inv_cols[j][i] for j in range(order)] for i in range(order)]
    return phi, s2, cov


def d2(x, order, beta=2, fit="yw", dt=1.0, err=False):
    """Distance to criticality of a series in bits per step (per unit time when dt is not 1).

    fit: "yw" (Yule-Walker, biased autocovariance), "yw_unbiased" (the authors' convention) or "ols".
    err=True adds the delta-method standard error of the paper's SI eq. 8 (uses the ols fit)."""
    if fit == "ols" or err:
        phi, s2, cov = fit_ols(x, order)
    else:
        phi, s2 = fit_yw(x, order, biased=(fit == "yw"))
        cov = None
    out = {"phi": phi, "sigma2": s2, "order": order, "beta": beta, "fit": fit, "dt": dt, "scope": list(SCOPE_D2)}
    if not is_stationary(phi):
        out.update(ok=False, d=float("nan"), why="fitted kernel not stationary")
        return out
    dn, phic = d_beta(phi, beta)
    out.update(ok=True, d=dn / LN2 / dt, phi_c=phic)
    if err:
        out["se"] = _se(phi, beta, cov) / LN2 / dt
    return out


def _se(phi, beta, cov, step=1e-4):
    base = d_beta(phi, beta)[0]
    grad = []
    for j in range(len(phi)):
        h = step
        p = list(phi)
        p[j] += h
        while not is_stationary(p) and h > 1e-9:
            h /= 10
            p = list(phi)
            p[j] += h
        grad.append((d_beta(p, beta)[0] - base) / h)
    v = sum(grad[i] * cov[i][j] * grad[j] for i in range(len(phi)) for j in range(len(phi)))
    return math.sqrt(max(v, 0.0))


def _kernel(bandwidth, causal):
    h = int(math.ceil(6 * bandwidth))
    lags = range(0, h + 1) if causal else range(-h, h + 1)
    return [(L, math.exp(-0.5 * (L / bandwidth) ** 2)) for L in lags]


def detrend(x, bandwidth, causal=True):
    """Residual after a Gaussian kernel smoother (sd = bandwidth samples), weights renormalised at the edges.

    causal=True uses x[t - L] for L >= 0 only, so no later value enters the residual at t."""
    x = [float(v) for v in x]
    k = _kernel(bandwidth, causal)
    out = []
    for t in range(len(x)):
        num = den = 0.0
        for L, w in k:
            i = t - L
            if 0 <= i < len(x):
                num += w * x[i]
                den += w
        out.append(x[t] - num / den)
    return out


def sliding(x, win, step, order, beta=2, fit="yw", detrend_bw=None, detrend_mode="causal"):
    """d2 in sliding windows; returns (window end indices, values in bits per step, nan where a fit fails).

    detrend_mode "causal" (default, for early-warning reads) or "gaussian" (two-sided)."""
    x = [float(v) for v in x]
    if detrend_bw:
        x = detrend(x, detrend_bw, causal=(detrend_mode == "causal"))
    ends, vals = [], []
    for e in range(win, len(x) + 1, step):
        try:
            v = d2(x[e - win: e], order, beta, fit)["d"]
        except ValueError:
            v = float("nan")
        ends.append(e - 1)
        vals.append(v)
    return ends, vals


def kendall_tau(y):
    """Kendall tau of y against its index (NaNs dropped): the usual early-warning trend statistic."""
    y = [v for v in y if v == v and math.isfinite(v)]
    n = len(y)
    if n < 3:
        return float("nan")
    s = sum((y[j] > y[i]) - (y[j] < y[i]) for i in range(n - 1) for j in range(i + 1, n))
    return s / (n * (n - 1) / 2)
