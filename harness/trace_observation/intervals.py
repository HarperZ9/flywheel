"""intervals.py -- Wilson intervals, paired bootstrap, exact sign test, Holm, minimum sample.

Every rate a component reports passes through here before a receipt. Values
leave as fixed four-place decimal strings so the receipt carries no floats. A
result below its declared minimum sample is a refusal (INSUFFICIENT_SAMPLE with
the n required), never a verdict, and a verdict is refused when its interval
straddles the threshold it would be judged against.
"""
from __future__ import annotations

import math
import random

Z95 = 1.959963984540054
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
STRADDLES = "INTERVAL_STRADDLES_THRESHOLD"


def fmt4(x: float) -> str:
    return f"{x:.4f}"


def wilson(k: int, n: int, z: float = Z95) -> tuple:
    """Wilson score interval for k successes in n trials."""
    if n <= 0:
        raise ValueError("wilson: n must be positive")
    if not 0 <= k <= n:
        raise ValueError("wilson: k must lie in [0, n]")
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def rate_block(k: int, n: int, *, minimum: int = 1) -> dict:
    """k, n, rate and Wilson bounds as strings; a refusal below the minimum."""
    if n < minimum:
        return {"status": INSUFFICIENT_SAMPLE, "k": str(k), "n": str(n), "n_required": str(minimum)}
    lo, hi = wilson(k, n)
    return {"status": "ok", "k": str(k), "n": str(n), "rate": fmt4(k / n),
            "lower": fmt4(lo), "upper": fmt4(hi), "method": "wilson-95"}


def paired_bootstrap(diffs: list, *, draws: int = 10000, seed: int = 7,
                     alpha: float = 0.05) -> dict:
    """Percentile interval on the mean of per-item paired differences."""
    if not diffs:
        raise ValueError("paired_bootstrap: no paired differences")
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(draws))
    lo = means[int((alpha / 2) * (draws - 1))]
    hi = means[int((1 - alpha / 2) * (draws - 1))]
    return {"point": fmt4(sum(diffs) / n), "lower": fmt4(lo), "upper": fmt4(hi), "n": str(n),
            "method": "paired-bootstrap-percentile", "draws": str(draws), "seed": str(seed)}


def sign_test(diffs: list) -> float:
    """Exact two-sided sign test over the nonzero paired differences."""
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    m = pos + neg
    if m == 0:
        return 1.0
    k = min(pos, neg)
    tail = sum(math.comb(m, i) for i in range(k + 1)) / 2 ** m
    return min(1.0, 2 * tail)


def holm(pvalues: dict, alpha: float = 0.05) -> dict:
    """Holm step-down. Returns name -> {p, p_adjusted, reject} with strings."""
    order = sorted(pvalues, key=lambda k: pvalues[k])
    m = len(order)
    out, running, stop = {}, 0.0, False
    for i, name in enumerate(order):
        adj = min(1.0, max(running, (m - i) * pvalues[name]))
        running = adj
        reject = (not stop) and adj < alpha
        stop = stop or not reject
        out[name] = {"p": fmt4(pvalues[name]), "p_adjusted": fmt4(adj),
                     "reject": "true" if reject else "false"}
    return out


def verdict_or_refusal(interval: dict, threshold: float, *, above: str, below: str) -> str:
    """A verdict only when the interval sits wholly on one side of the threshold."""
    lo, hi = float(interval["lower"]), float(interval["upper"])
    if lo > threshold:
        return above
    if hi < threshold:
        return below
    return STRADDLES


def upper_bound_statement(k: int, n: int) -> str:
    """What a null bounds, stated with its denominator (critic item 1)."""
    if n == 0:
        return "no items in the denominator; the arm bounds nothing"
    _, hi = wilson(k, n)
    return f"{k}/{n} changed; Wilson 95% upper bound {fmt4(hi)}; a null bounds effects only above that"
