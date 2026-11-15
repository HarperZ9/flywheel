"""A3 — carry the depth law toward a LAW: robustness across families + DERIVE the +0.07.

Established: fair-adversary tolerance f* ~ 1/(1+rho) + 0.07 (run_gaps.py), fitted in ONE family
(K=0.30, Gaussian wells, mask p=0.7, N=12). Two questions:
  (1) Does the FORM (falls as 1/(1+rho)) survive other families? Vary K and N.
  (2) Can the additive bonus c be DERIVED? Hypothesis: c is the 'coverage bonus' from sight-
      sharing -- honest agents collectively see dims a single agent is blind to, so the commons
      tolerates slightly more than the bare depth ratio predicts. If so, c should track the mask
      coverage: c grows as agents see MORE (mask p up), shrinks as they see less. We sweep mask p
      and fit c(p). A monotone c(p) rising with coverage = the bonus is coverage, derived not fitted.

Stdlib, seeded, deterministic. Fair (sincere, damped) adversary, mean aggregation, mid start.
"""
from __future__ import annotations
import math, random, statistics

D, STEPS, SIGMA, SEP = 8, 500, 2.2, 3.0


def _sub(a, b): return [x - y for x, y in zip(a, b)]
def _add(a, b): return [x + y for x, y in zip(a, b)]
def _scale(a, s): return [x * s for x in a]
def _dist(a, b): return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
def _mean(vs): return [sum(c) / len(vs) for c in zip(*vs)]


def make_world(seed, maskp, N):
    rng = random.Random(seed)
    t = [rng.uniform(-1, 1) for _ in range(D)]
    q = _add(t, [rng.choice([-1, 1]) * SEP for _ in range(D)])
    masks = [[1 if rng.random() < maskp else 0 for _ in range(D)] for _ in range(N)]
    for j in range(D):
        if not any(masks[i][j] for i in range(N)):
            masks[rng.randrange(N)][j] = 1
    return t, q, masks


def well_grad(x, c, mask, sigma, w):
    d2 = sum((c[j] - x[j]) ** 2 for j in range(D))
    p = w * math.exp(-d2 / (2 * sigma ** 2))
    return [p * (c[j] - x[j]) * mask[j] for j in range(D)]


def run(t, q, masks, n_adv, rho, K, LR=0.15):
    N = len(masks)
    rng = random.Random(99)
    mid = _mean([t, q])
    agents = [_add(mid, [rng.uniform(-1, 1) for _ in range(D)]) for _ in range(N)]
    advs = set(range(n_adv))
    for _ in range(STEPS):
        bar = _mean(agents)
        new = []
        for i, x in enumerate(agents):
            c, w = (q, rho) if i in advs else (t, 1.0)   # fair: adversary climbs its own decoy field
            v = _scale(well_grad(x, c, masks[i], SIGMA, w), LR)
            new.append(_add(_add(x, v), _scale(_sub(bar, x), K)))
        agents = new
    bar = _mean(agents)
    return _dist(bar, t) < _dist(bar, q)


def fstar(t, q, masks, rho, K):
    N = len(masks)
    for n in range(N + 1):
        if not run(t, q, masks, n, rho, K):
            return n / N
    return 1.0


def fit_c(seeds, rhos, maskp, N, K):
    resid = []
    for rho in rhos:
        m = statistics.mean(fstar(*make_world(s, maskp, N), rho, K) for s in seeds)
        resid.append(m - 1.0 / (1.0 + rho))
    return statistics.mean(resid), statistics.pstdev(resid)


def main():
    seeds = [7, 11, 19, 23]
    rhos = [0.3, 0.5, 0.7, 1.0, 1.3]

    print("A3.1 — does the FORM 1/(1+rho) survive other families? (residual c should stay")
    print("       small + ~constant; if the form broke, residual would swing with rho)\n")
    print("   family                         mean resid c    std")
    for label, N, K in [("baseline N=12 K=0.30", 12, 0.30),
                        ("weak consensus K=0.15", 12, 0.15),
                        ("strong consensus K=0.45", 12, 0.45),
                        ("small commons N=6", 6, 0.30),
                        ("large commons N=20", 20, 0.30)]:
        c, sd = fit_c(seeds, rhos, 0.7, N, K)
        print(f"   {label:30s}  {c:+.3f}        {sd:.3f}")

    print("\nA3.2 — DERIVE the bonus: sweep mask coverage p; does c track coverage?")
    print("       (if c rises with p, the +bonus IS shared-sight coverage, not a free constant)\n")
    print("   mask p   approx single-agent blind%   mean resid c")
    for p in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        c, _ = fit_c(seeds, rhos, p, 12, 0.30)
        print(f"   {p:4.2f}        {100*(1-p):4.0f}%                  {c:+.3f}")
    print("\n  READ: form-robust if c stays small across families. Bonus 'derived' if c rises")
    print("  monotonically with mask p (more shared sight -> more tolerance over the bare law),")
    print("  and -> ~0 at p=1.0 (full sight: nothing left for consensus to recover -> no bonus).")


if __name__ == "__main__":
    main()
