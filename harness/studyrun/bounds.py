"""Bound-violation rule: did any arm beat its ceiling, after allowing for the number of arms tested?

Standard library only, like the stage. A test is (k successes, n trials, bound). The p-value is the exact
one-sided binomial tail P(X >= k | n, bound), the worst case for a true ceiling. The default family
correction is Holm (family-wise error at alpha); Bonferroni and Benjamini-Hochberg are available.

Why: F79's per-test Wald rule flags about 18 of 756 tests by chance when every arm sits at its bound
(F80). Formula round 1 (2026-10-29, C5) checked this rule's calibration on held-out configurations.

Use from an analysis unit:
    from studyrun.bounds import violations
    flags, p = violations([(k1, n1, b1), (k2, n2, b2), ...])
and put the count of flags in the analysis result for a verdict rule such as
    {"left": "analysis.bound_flags", "op": "<=", "right": 0}.
"""
import math


def binom_sf(k, n, p):
    """P(X >= k) for X ~ Binomial(n, p), summed in log space."""
    if k <= 0:
        return 1.0
    if k > n or p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    lp, lq = math.log(p), math.log1p(-p)
    terms = [math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * lp + (n - j) * lq
             for j in range(k, n + 1)]
    top = max(terms)
    return min(1.0, math.exp(top) * math.fsum(math.exp(t - top) for t in terms))


def exact_p(k, n, bound):
    return 1.0 if bound >= 1 else binom_sf(k, n, bound)


def holm(ps, alpha=0.05):
    m = len(ps)
    flags = [False] * m
    for rank, i in enumerate(sorted(range(m), key=lambda j: ps[j])):
        if ps[i] * (m - rank) > alpha:
            break
        flags[i] = True
    return flags


def bonferroni(ps, alpha=0.05):
    return [p * len(ps) <= alpha for p in ps]


def bh(ps, q=0.05):
    m = len(ps)
    order = sorted(range(m), key=lambda j: ps[j])
    last = max((r for r, i in enumerate(order, 1) if ps[i] <= q * r / m), default=0)
    flags = [False] * m
    for i in order[:last]:
        flags[i] = True
    return flags


RULES = {"holm": holm, "bonferroni": bonferroni, "bh": bh}


def violations(tests, alpha=0.05, method="holm"):
    """tests: iterable of (k, n, bound). Returns (flags, p-values), both in input order."""
    if method not in RULES:
        raise ValueError(f"method must be one of {sorted(RULES)}")
    ps = [exact_p(int(k), int(n), float(b)) for k, n, b in tests]
    return RULES[method](ps, alpha), ps
