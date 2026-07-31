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
from math import comb, sqrt

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
