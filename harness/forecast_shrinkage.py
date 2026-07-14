"""forecast_shrinkage.py -- correct the forecast point bias at its source.

The k=5 replication showed the per-task Jeffreys forecast ran high on both
independent runs. The cause is a winner's curse: a single seed run's
empirical rate c/n overstates a task's true success probability for tasks
that passed by luck (a task that hit on attempt 1 looks like p=1.0). The
bootstrap widened the interval but could not re-centre it, because the
CENTRE was biased, not just the width.

Empirical-Bayes shrinkage corrects the centre. It fits a population
Beta(alpha, beta) to the per-task counts by method of moments, then
replaces each task's raw rate with its posterior mean under that
population prior, (alpha + c_i) / (alpha + beta + n_i). A task with little
data (small n) is pulled hard toward the pool; a lucky 1/1 no longer
forecasts 1.0. Heterogeneous data leaves room to shrink; homogeneous data
does not, and the shrinkage is then near a no-op, honestly. Pure and
deterministic.
"""
from __future__ import annotations

SCHEMA = "flywheel.forecast-shrinkage/v1"


def shrink_rates(rows: list) -> dict:
    """Return per-task shrunk success rates plus the fitted population
    prior. `rows` is [{task_id, n, c}]."""
    if not rows:
        return {"schema": SCHEMA, "error": "no rows to shrink"}
    raw = [(r["c"] / r["n"]) if r["n"] else 0.0 for r in rows]
    T = len(raw)
    mbar = sum(raw) / T
    var = sum((p - mbar) ** 2 for p in raw) / T if T > 1 else 0.0
    # method-of-moments Beta fit: only when there is real between-task
    # spread AND it is below the binomial ceiling mbar(1-mbar); otherwise
    # fall back to a weak prior (large concentration => little shrinkage)
    ceiling = mbar * (1.0 - mbar)
    if 0.0 < var < ceiling:
        concentration = ceiling / var - 1.0
    else:
        concentration = 1e6   # effectively no shrinkage room
    alpha = mbar * concentration
    beta = (1.0 - mbar) * concentration
    out = []
    for r, p in zip(rows, raw):
        shrunk = (alpha + r["c"]) / (alpha + beta + r["n"])
        out.append({"task_id": r.get("task_id", ""), "n": r["n"], "c": r["c"],
                    "raw": round(p, 4), "shrunk": round(shrunk, 4)})
    return {"schema": SCHEMA, "rows": out, "pool_mean": round(mbar, 4),
            "prior_alpha": round(alpha, 4), "prior_beta": round(beta, 4),
            "n_tasks": T,
            "note": "each raw rate is replaced by its posterior mean under a "
                    "population Beta fit to the pool; a lucky low-n task is "
                    "pulled toward the pool, correcting the winner's-curse "
                    "optimism the interval could not re-centre"}
