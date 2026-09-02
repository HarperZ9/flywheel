"""statistics.py -- section 6: the variance component, the interval, and the MDE.

Four requirements the frozen preregistration states and nothing in this
repository computed. Each is implemented so the honest refusal is the easy path
and the misleading number is the one you cannot get.

  * **The primary variance component is BETWEEN-SEED**, from r = 3 full pipeline
    replicates minimum. One confirmatory pass is r = 1, so this module refuses to
    return a between-seed SD from it rather than returning something smaller that
    would read like one.
  * **A range is not an SD.** The prereg says so in as many words, with the
    arithmetic: E[range] at n = 2 is 1.128 sigma, so a 2.7 point two-run spread
    implies sigma near 2.4, not 1.35. Halving a range is the mistake this guards,
    and the conversion that IS correct is available, labelled.
  * **Standard errors clustered** by difficulty band and generator seed. The
    generator emits related groups, so unclustered errors are anticonservative.
  * **A declared MDE next to every result, including every null**, because
    without one "no effect" and "no power" read identically.

The MDE here is exact rather than approximate: it asks the same binomial the
paired test asks, and reports the smallest split that test could have called.

Stdlib only. Every function is deterministic given its seed.
"""
from __future__ import annotations

import random
from math import comb, exp, lgamma, log, sqrt

SCHEMA = "flywheel.statistics/v1"

# E[range] / sigma for a normal sample. Used ONLY by the labelled range
# conversion below. Values are the standard d2 control-chart constants.
_D2 = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534, 7: 2.704}

MIN_REPLICATES = 3


class StatisticsError(ValueError):
    """A statistic that cannot be computed without misleading whoever reads it."""


def between_seed_sd(values, *, minimum: int = MIN_REPLICATES) -> dict:
    """The primary variance component, or a refusal naming what is missing.

    `values` are one summary per FULL PIPELINE replicate, not per instance and
    not per sampling seed within a pass. Conflating those is the whole reason
    this function takes a list and counts it.
    """
    vals = [float(v) for v in values]
    if len(vals) < minimum:
        raise StatisticsError(
            f"a between-seed SD needs at least {minimum} full pipeline "
            f"replicates and got {len(vals)}. One confirmatory pass is r=1, and "
            "the within-pass sampling seeds are not replicates of the pipeline: "
            "reporting their spread as the between-seed component would "
            "understate the quantity the prereg calls primary.")
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return {"schema": SCHEMA, "statistic": "between_seed_sd",
            "n_replicates": len(vals), "mean": round(mean, 6),
            "sd": round(sqrt(var), 6),
            "does_not_prove": [
                "NOT_PROVES_STABILITY_ACROSS_ENVIRONMENTS: replicates of one "
                "pipeline on one machine bound sampling noise, not portability.",
            ]}


def sd_from_range(range_width: float, n: int) -> dict:
    """Estimate sigma from a range, with the right constant and a loud label.

    Halving a range is the error the prereg calls out by name. At n = 2 the
    expected range is 1.128 sigma, so a 2.7 point spread implies sigma near 2.4
    and not 1.35. This returns the correct estimate and marks it as
    range-derived, because a range-derived sigma at n = 2 is itself very noisy
    and must never be presented as an SD over replicates.
    """
    if n not in _D2:
        raise StatisticsError(
            f"no range-to-sigma constant for n={n}; supported: {sorted(_D2)}")
    if range_width < 0:
        raise StatisticsError("a range cannot be negative")
    return {"schema": SCHEMA, "statistic": "sd_from_range",
            "n": n, "range": round(float(range_width), 6),
            "d2": _D2[n], "sigma_estimate": round(range_width / _D2[n], 6),
            "estimator": "range/d2",
            "does_not_prove": [
                "NOT_PROVES_A_REPLICATE_SD: this is derived from a range, not "
                f"from {MIN_REPLICATES} or more replicates, and at small n it is "
                "a very noisy estimate of sigma.",
                "NOT_HALF_THE_RANGE: half a range understates sigma at every n "
                "in the table, which is the specific error this exists to stop.",
            ]}


def cluster_bootstrap(clusters, statistic, *, draws: int = 2000,
                      seed: int = 0, alpha: float = 0.05) -> dict:
    """Hierarchical bootstrap: resample CLUSTERS, then units within each.

    `clusters` maps a cluster key to its list of units. The prereg clusters by
    difficulty band and generator seed, because the generator emits related
    groups and treating their units as independent is anticonservative.

    `statistic` takes the flattened unit list and returns a number.
    """
    keys = sorted(clusters)
    if len(keys) < 2:
        raise StatisticsError(
            "a cluster bootstrap needs at least two clusters; with one cluster "
            "the resample cannot vary and the interval would be a point "
            "pretending to be a range")
    if not 0.0 < alpha < 1.0:
        raise StatisticsError(f"alpha must sit in (0,1), got {alpha}")
    rng = random.Random(seed)
    stats = []
    for _ in range(int(draws)):
        units = []
        for _ in range(len(keys)):
            key = keys[rng.randrange(len(keys))]      # outer: clusters
            pool = clusters[key]
            if not pool:
                continue
            units.extend(pool[rng.randrange(len(pool))]  # inner: units
                         for _ in range(len(pool)))
        if units:
            stats.append(float(statistic(units)))
    if not stats:
        raise StatisticsError("every bootstrap draw was empty")
    stats.sort()
    lo = stats[int((alpha / 2) * (len(stats) - 1))]
    hi = stats[int((1 - alpha / 2) * (len(stats) - 1))]
    return {"schema": SCHEMA, "statistic": "cluster_bootstrap",
            "n_clusters": len(keys), "draws": len(stats),
            "alpha": f"{alpha:.4f}",
            "point": round(float(statistic([u for k in keys
                                            for u in clusters[k]])), 6),
            "interval": [round(lo, 6), round(hi, 6)],
            "does_not_prove": [
                "NOT_PROVES_BETWEEN_SEED_COVERAGE: resampling within ONE "
                "pipeline pass carries task-population and within-cluster "
                "variance. It does not carry the between-seed component, which "
                "needs replicate passes and which the prereg calls primary.",
            ]}


def mcnemar_mde(n_pairs: int, n_discordant: int, *, alpha: float = 0.05) -> dict:
    """The smallest paired difference the exact test could have called here.

    Exact rather than approximate: it asks the same binomial the paired test
    asks, and walks the splits until one is significant. With arms sharing a
    cached pool the binding quantity is the discordant count, not the task
    count, and the two are reported side by side so a reader can see how far
    apart they are.
    """
    if n_pairs <= 0:
        raise StatisticsError("no pairs, no minimum detectable effect")
    if not 0 <= n_discordant <= n_pairs:
        raise StatisticsError(
            f"{n_discordant} discordant of {n_pairs} pairs is impossible")
    m = int(n_discordant)
    detectable = None
    for k in range(m // 2, -1, -1):                  # k = the smaller cell
        p = min(1.0, 2 * sum(comb(m, i) for i in range(k + 1)) / 2 ** m) if m else 1.0
        if p <= alpha:
            detectable = m - 2 * k                   # |b - c| at that split
            break
    out = {"schema": SCHEMA, "statistic": "mcnemar_mde",
           "n_pairs": n_pairs, "n_discordant": m, "alpha": f"{alpha:.4f}",
           "does_not_prove": [
               "NOT_PROVES_AN_EFFECT_IS_ABSENT: an MDE describes what this "
               "design could have seen. A null below it is uninformative, not "
               "negative.",
           ]}
    if detectable is None:
        out["detectable"] = None
        out["mde_delta"] = None
        out["note"] = (
            f"NO SPLIT of {m} discordant pair(s) reaches alpha={alpha}. This "
            "design cannot produce a significant paired result at any effect "
            "size, so a null here carries no information about the effect.")
    else:
        out["detectable"] = detectable
        out["mde_delta"] = round(detectable / n_pairs, 6)
        out["note"] = (
            f"with {m} discordant pair(s), the smallest callable imbalance is "
            f"{detectable}, i.e. a paired difference of "
            f"{detectable / n_pairs:.4f} over {n_pairs} pairs")
    return out


def _mcnemar_critical_k(m: int, alpha: float):
    """Largest smaller-cell count whose two-sided exact p meets alpha, or None.

    Same binomial `mcnemar_mde` asks, from the other side: the two-sided exact
    p grows with k, so the significant splits form a prefix [0..k] and the scan
    stops at the first k past it.
    """
    cum = 0
    total = 2 ** m
    best = None
    c = 1                                            # comb(m, 0)
    for k in range(0, m // 2 + 1):
        if k > 0:
            c = c * (m - k + 1) // k                 # comb(m, k), exact
        cum += c
        if min(1.0, 2 * cum / total) <= alpha:
            best = k
        else:
            break
    return best


def _binomial_tail_mass(m: int, k_crit: int, p1: float) -> float:
    """P(B <= k_crit) + P(B >= m - k_crit) for B ~ Binomial(m, p1).

    Log-space pmf, because (1 - p1) ** m underflows long before the plan sizes
    stop being realistic.
    """
    if p1 >= 1.0:
        return 1.0
    lp, lq, lgm = log(p1), log(1.0 - p1), lgamma(m + 1)

    def pmf(b: int) -> float:
        return exp(lgm - lgamma(b + 1) - lgamma(m - b + 1)
                   + b * lp + (m - b) * lq)

    return (sum(pmf(b) for b in range(0, k_crit + 1))
            + sum(pmf(b) for b in range(m - k_crit, m + 1)))


def mcnemar_plan(target_delta: float, *, alpha: float = 0.05,
                 power: float = 0.8,
                 recorded_discordant_fraction: float | None = None,
                 max_pairs: int = 20000) -> dict:
    """The task-level N of pairs a future exact McNemar needs, or a refusal.

    Inverse of `mcnemar_mde`: given a target paired delta, alpha, power, and a
    discordant fraction, find the smallest N whose expected discordant count
    gives the exact test at least the requested power against that delta, with
    the design's own MDE at or under the target.

    THE BASIS REQUIREMENT: `recorded_discordant_fraction` must be a fraction
    RECORDED from a prior run of the same instrument (e.g. the pilot's
    published per-task discordance). It has no default worth using; when it is
    absent this function refuses, because sizing a decisive run from an
    assumed discordance is a forking path -- the assumption would be chosen
    after seeing what N it buys. A recorded basis is a fact; an assumed one is
    a knob.

    Sizing is conservative in one deliberate place: the expected discordant
    count is the FLOOR of fraction * N. Under the alternative the discordant
    pairs split with probability (1 + delta/fraction) / 2 toward the better
    arm, which also bounds the target: a paired delta cannot exceed the
    discordant fraction.
    """
    if recorded_discordant_fraction is None:
        raise StatisticsError(
            "mcnemar_plan refuses to size a run without a recorded discordance "
            "basis. Supply recorded_discordant_fraction from a prior recorded "
            "run of this instrument; sizing from an assumed discordance is a "
            "forking path, and this refusal is the guard against it.")
    f = float(recorded_discordant_fraction)
    if not 0.0 < f <= 1.0:
        raise StatisticsError(
            f"a discordant fraction must sit in (0, 1], got {f}. Zero recorded "
            "discordance sizes nothing: no discordant pairs, no paired test.")
    d = float(target_delta)
    if not 0.0 < d <= f:
        raise StatisticsError(
            f"target delta {d} is not in (0, {f}]. A paired delta cannot "
            "exceed the discordant fraction: |b - c| <= b + c.")
    if not 0.0 < alpha < 1.0:
        raise StatisticsError(f"alpha must sit in (0,1), got {alpha}")
    if not 0.0 < power < 1.0:
        raise StatisticsError(f"power must sit in (0,1), got {power}")
    if int(max_pairs) < 1:
        raise StatisticsError(f"max_pairs must be positive, got {max_pairs}")

    p1 = 0.5 * (1.0 + d / f)

    def achieved(n: int):
        """(m, k_crit, achieved_power) when n satisfies the plan, else None."""
        m = int(f * n)
        if m < 1:
            return None
        k = _mcnemar_critical_k(m, alpha)
        if k is None:
            return None
        if (m - 2 * k) / n > d:                      # MDE must not exceed target
            return None
        pw = _binomial_tail_mass(m, k, p1)
        return (m, k, pw) if pw >= power else None

    n = 1
    while n <= int(max_pairs) and achieved(n) is None:
        n *= 2
    if n > int(max_pairs):
        raise StatisticsError(
            f"no N of pairs up to max_pairs={int(max_pairs)} reaches power "
            f"{power} for delta {d} at alpha {alpha} on a recorded discordant "
            f"fraction of {f}. Raise max_pairs deliberately or accept that "
            "the target is out of reach at this discordance.")
    lo, hi = n // 2, n
    while lo + 1 < hi:                               # quasi-monotone bisection
        mid = (lo + hi) // 2
        if achieved(mid) is not None:
            hi = mid
        else:
            lo = mid
    n = hi
    while n > 1 and achieved(n - 1) is not None:     # tighten past discreteness
        n -= 1
    m, k_crit, achieved_power = achieved(n)
    return {"schema": SCHEMA, "statistic": "mcnemar_plan",
            "n_pairs": n, "expected_discordant": m,
            "target_delta": round(d, 6), "alpha": f"{alpha:.4f}",
            "power_target": f"{power:.4f}",
            "achieved_power": round(achieved_power, 6),
            "discordance_basis": {
                "recorded_discordant_fraction": round(f, 6)},
            "mde_at_plan": mcnemar_mde(n, m, alpha=alpha),
            "note": (
                f"the smallest N whose floor({f} * N) = {m} expected "
                f"discordant pair(s) give the exact test power "
                f"{achieved_power:.4f} against delta {d}; N - 1 fails at "
                "least one plan condition."),
            "does_not_prove": [
                "NOT_PROVES_THE_NEXT_RUN_MATCHES_THE_BASIS: the plan holds "
                "only as far as the future run's discordance resembles the "
                "recorded fraction; discord less, and the achieved power "
                "falls with it.",
            ]}
