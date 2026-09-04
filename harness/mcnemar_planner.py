"""Prospective sample-size planning for paired exact McNemar comparisons.

The planner stays separate from the descriptive statistics module because it
answers a design question: how many task pairs a future run needs. It requires
a discordance fraction recorded by the same instrument and refuses to invent
that basis.
"""
from __future__ import annotations

from math import exp, lgamma, log

from .statistics import SCHEMA, StatisticsError, mcnemar_mde


def _critical_k(m: int, alpha: float):
    """Largest smaller-cell count whose two-sided exact p meets alpha."""
    cumulative = 0
    total = 2 ** m
    best = None
    coefficient = 1
    for k in range(0, m // 2 + 1):
        if k > 0:
            coefficient = coefficient * (m - k + 1) // k
        cumulative += coefficient
        if min(1.0, 2 * cumulative / total) <= alpha:
            best = k
        else:
            break
    return best


def _tail_mass(m: int, k_crit: int, p1: float) -> float:
    """Return both rejection-tail masses for ``Binomial(m, p1)``."""
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
    """Return the smallest future paired-task count meeting the exact design.

    ``recorded_discordant_fraction`` must come from a prior run of the same
    instrument. The expected discordant count is conservatively floored, and a
    target paired delta cannot exceed the recorded discordant fraction.
    """
    if recorded_discordant_fraction is None:
        raise StatisticsError(
            "mcnemar_plan refuses to size a run without a recorded discordance "
            "basis. Supply recorded_discordant_fraction from a prior recorded "
            "run of this instrument; sizing from an assumed discordance is a "
            "forking path, and this refusal is the guard against it.")
    fraction = float(recorded_discordant_fraction)
    if not 0.0 < fraction <= 1.0:
        raise StatisticsError(
            f"a discordant fraction must sit in (0, 1], got {fraction}. Zero "
            "recorded discordance sizes nothing: no discordant pairs, no "
            "paired test.")
    delta = float(target_delta)
    if not 0.0 < delta <= fraction:
        raise StatisticsError(
            f"target delta {delta} is not in (0, {fraction}]. A paired delta "
            "cannot exceed the discordant fraction: |b - c| <= b + c.")
    if not 0.0 < alpha < 1.0:
        raise StatisticsError(f"alpha must sit in (0,1), got {alpha}")
    if not 0.0 < power < 1.0:
        raise StatisticsError(f"power must sit in (0,1), got {power}")
    if int(max_pairs) < 1:
        raise StatisticsError(f"max_pairs must be positive, got {max_pairs}")

    p1 = 0.5 * (1.0 + delta / fraction)

    def achieved(n: int):
        expected = int(fraction * n)
        if expected < 1:
            return None
        critical = _critical_k(expected, alpha)
        if critical is None:
            return None
        if (expected - 2 * critical) / n > delta:
            return None
        achieved_power = _tail_mass(expected, critical, p1)
        if achieved_power < power:
            return None
        return expected, critical, achieved_power

    plan = None
    for n_pairs in range(1, int(max_pairs) + 1):
        plan = achieved(n_pairs)
        if plan is not None:
            break
    if plan is None:
        raise StatisticsError(
            f"no N of pairs up to max_pairs={int(max_pairs)} reaches power "
            f"{power} for delta {delta} at alpha {alpha} on a recorded "
            f"discordant fraction of {fraction}. Raise max_pairs deliberately "
            "or accept that the target is out of reach at this discordance.")

    expected, _critical, achieved_power = plan
    return {
        "schema": SCHEMA,
        "statistic": "mcnemar_plan",
        "n_pairs": n_pairs,
        "expected_discordant": expected,
        "target_delta": round(delta, 6),
        "alpha": f"{alpha:.4f}",
        "power_target": f"{power:.4f}",
        "achieved_power": round(achieved_power, 6),
        "discordance_basis": {
            "recorded_discordant_fraction": round(fraction, 6),
        },
        "mde_at_plan": mcnemar_mde(n_pairs, expected, alpha=alpha),
        "note": (
            f"the smallest N whose floor({fraction} * N) = {expected} "
            f"expected discordant pair(s) give the exact test power "
            f"{achieved_power:.4f} against delta {delta}; N - 1 fails at "
            "least one plan condition."
        ),
        "does_not_prove": [
            "NOT_PROVES_THE_NEXT_RUN_MATCHES_THE_BASIS: the plan holds only "
            "as far as the future run's discordance resembles the recorded "
            "fraction; discord less, and the achieved power falls with it.",
        ],
    }
