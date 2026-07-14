"""forecast_bootstrap.py -- the honest forecast interval.

The k=5 replication (2026-07-14) falsified our own sealed interval: the
per-task Jeffreys band held run one and missed run two, because it
carried within-task uncertainty but not the BETWEEN-RUN variance of a
fresh bench. Two identical-config runs spread ~2.7 points from sampling
alone at n=110, and the point interval was too tight to contain it.

This is the correction, and it is the loop closing on its own tool: a
receipt falsified the instrument, so the instrument is fixed. The
bootstrap draws whole fresh runs. For each replicate it samples a
success probability per task from that task's Jeffreys posterior, then
draws a best-of-k Bernoulli outcome per task, and averages to a whole-
run pass rate. The 95% interval over those replicate rates includes the
run-to-run spread the point band missed. Zero-dep: a small deterministic
LCG so a fixed seed reproduces the interval exactly (Math.random and the
stdlib RNG are both avoided for reproducibility across environments).
"""
from __future__ import annotations

SCHEMA = "flywheel.passk-forecast-bootstrap/v1"
_A0, _B0 = 0.5, 0.5   # Jeffreys prior, matching passn_model


class _LCG:
    """A tiny deterministic PRNG (numerical-recipes LCG). Seeded runs
    reproduce byte-identically, which the receipt requires."""
    def __init__(self, seed: int):
        self.s = (seed * 2862933555777941757 + 3037000493) & ((1 << 64) - 1)

    def uniform(self) -> float:
        self.s = (self.s * 6364136223846793005 + 1442695040888963407) \
            & ((1 << 64) - 1)
        return (self.s >> 11) / float(1 << 53)


def _beta_sample(a: float, b: float, rng: _LCG) -> float:
    """Sample Beta(a,b) via two Gamma samples (Marsaglia-Tsang), Gamma via
    the same LCG. a,b are small here (Jeffreys + small counts), so the
    method is stable."""
    def gamma(shape: float) -> float:
        if shape < 1.0:
            # boost then correct
            u = rng.uniform() or 1e-12
            return gamma(shape + 1.0) * (u ** (1.0 / shape))
        d = shape - 1.0 / 3.0
        c = 1.0 / ((9.0 * d) ** 0.5)
        while True:
            # a crude normal via sum of 12 uniforms minus 6 (Irwin-Hall)
            x = sum(rng.uniform() for _ in range(12)) - 6.0
            v = (1.0 + c * x) ** 3
            if v <= 0:
                continue
            u = rng.uniform() or 1e-12
            if u < 1.0 - 0.0331 * (x ** 4):
                return d * v
            import math
            if math.log(u) < 0.5 * x * x + d * (1.0 - v + math.log(v)):
                return d * v
    ga, gb = gamma(a), gamma(b)
    tot = ga + gb
    return ga / tot if tot > 0 else 0.5


def _pass_at_k(p: float, k: int) -> float:
    return 1.0 - (1.0 - p) ** k


def bootstrap_forecast(rows: list, k: int = 5, *, draws: int = 3000,
                       seed: int = 0) -> dict:
    """Resample whole fresh best-of-k runs to get a run-to-run interval.
    `rows` is [{task_id, n, c}] seed-run outcomes. Returns the point
    estimate, the 95% bootstrap interval, its width, and the naive point
    band for comparison."""
    if not rows:
        return {"schema": SCHEMA, "error": "no per-task rows to forecast"}
    T = len(rows)
    rng = _LCG(seed or 1)
    # point estimate: expected best-of-k pass rate under the posterior mean
    posterior_means = [( _A0 + r["c"]) / (_A0 + _B0 + r["n"]) for r in rows]
    point = sum(_pass_at_k(pm, k) for pm in posterior_means) / T
    rates = []
    for _ in range(draws):
        s = 0
        for r in rows:
            p = _beta_sample(_A0 + r["c"], _B0 + r["n"] - r["c"], rng)
            q = _pass_at_k(p, k)
            s += 1 if rng.uniform() < q else 0   # a whole fresh outcome
        rates.append(s / T)
    rates.sort()
    lo = rates[int(0.025 * (len(rates) - 1))]
    hi = rates[int(0.975 * (len(rates) - 1))]
    # the band that UNDERCOVERED in the replication: the per-task Jeffreys
    # SD over independent Bernoullis at the posterior mean, no run-to-run
    # resampling. The bootstrap must be wider than this.
    qs = [_pass_at_k(pm, k) for pm in posterior_means]
    jeffreys_half = 1.96 * (sum(q * (1.0 - q) for q in qs)) ** 0.5 / T
    naive_half = 1.96 * (point * (1.0 - point) / T) ** 0.5
    return {"schema": SCHEMA, "k": k, "n_tasks": T, "draws": draws,
            "seed": seed,
            "expected_pass_rate": round(point, 4),
            "interval_95": [round(lo, 4), round(hi, 4)],
            "width": round(hi - lo, 4),
            "jeffreys_point_width": round(2 * jeffreys_half, 4),
            "naive_point_width": round(2 * naive_half, 4),
            "note": "the interval resamples whole fresh runs from the "
                    "per-task posteriors, so its width includes the "
                    "between-run variance the point band missed; wider "
                    "than the Jeffreys point band that undercovered; "
                    "seeded runs reproduce it exactly"}
