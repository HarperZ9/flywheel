"""Close the two simulable gaps: (1) does the gate's edge survive high dimension?
(2) what does the fair-adversary boundary actually fit — is it 1/(1+rho) or with a bonus?

Geometry is held CONSTANT across D: well separation S fixed (per-dim offset S/sqrt(D)),
sigma fixed relative to S. So only the dimensionality of the consensus/median operation
changes — isolating the known worry that coordinate-wise median degrades in high D.

Stdlib, seeded, deterministic.
"""
from __future__ import annotations

import math
import random
import statistics

N = 12
STEPS = 400
LR = 0.15
K = 0.30
S = 8.485        # well separation, held constant across D
SIGMA = 2.2


def _sub(a, b): return [x - y for x, y in zip(a, b)]
def _add(a, b): return [x + y for x, y in zip(a, b)]
def _scale(a, s): return [x * s for x in a]
def _dist(a, b): return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
def _mean(vs): return [sum(c) / len(vs) for c in zip(*vs)]
def _median(vs): return [statistics.median(c) for c in zip(*vs)]


def _trimmed(vs, frac=0.25):
    out = []
    k = int(len(vs) * frac)
    for col in zip(*vs):
        s = sorted(col)
        s = s[k:len(s) - k] or s
        out.append(sum(s) / len(s))
    return out


def agg(vs, mode):
    return {"mean": _mean, "median": _median, "trimmed": _trimmed}[mode](vs)


def make_world(seed, D):
    rng = random.Random(seed)
    off = S / math.sqrt(D)                       # keep ||t-q|| = S for all D
    t = [rng.uniform(-1, 1) for _ in range(D)]
    q = _add(t, [rng.choice([-1, 1]) * off for _ in range(D)])
    masks = [[1 if rng.random() < 0.7 else 0 for _ in range(D)] for _ in range(N)]
    for j in range(D):
        if not any(masks[i][j] for i in range(N)):
            masks[rng.randrange(N)][j] = 1
    return t, q, masks


def well_grad(x, c, mask, w, D):
    d2 = sum((c[j] - x[j]) ** 2 for j in range(D))
    p = w * math.exp(-d2 / (2 * SIGMA ** 2))
    return [p * (c[j] - x[j]) * mask[j] for j in range(D)]


def run(t, q, masks, n_adv, D, *, w_decoy, mode, adv):
    rng = random.Random(99)
    mid = _mean([t, q])
    agents = [_add(mid, [rng.uniform(-1, 1) for _ in range(D)]) for _ in range(N)]
    advs = set(range(n_adv))
    for _ in range(STEPS):
        bar = agg(agents, mode)
        new = []
        for i, x in enumerate(agents):
            if i in advs:
                v = (_scale(_sub(q, x), LR) if adv == "undamped"
                     else _scale(well_grad(x, q, masks[i], w_decoy, D), LR))
            else:
                v = _scale(well_grad(x, t, masks[i], 1.0, D), LR)
            new.append(_add(_add(x, v), _scale(_sub(bar, x), K)))
        agents = new
    bar = _mean(agents)
    return _dist(bar, t) < _dist(bar, q)


def fstar(t, q, masks, D, **kw):
    for n in range(N + 1):
        if not run(t, q, masks, n, D, **kw):
            return n / N
    return 1.0


def main():
    seeds = [7, 11, 19, 23]

    print("=" * 70)
    print("GAP 1: does the GATE's edge survive dimensionality? (geometry held const)")
    print("  f* (mean over seeds), coordinated UNDAMPED adversary, rho=0.6")
    print("=" * 70)
    print("    D      mean     median    trimmed     gate gain (median-mean)")
    for D in (2, 8, 32, 64):
        res = {}
        for mode in ("mean", "median", "trimmed"):
            res[mode] = statistics.mean(
                fstar(*make_world(s, D), D, w_decoy=0.6, mode=mode, adv="undamped") for s in seeds)
        print(f"   {D:3d}    {res['mean']:.2f}      {res['median']:.2f}      "
              f"{res['trimmed']:.2f}        {res['median'] - res['mean']:+.2f}")
    print("  (if gate gain shrinks toward 0 as D grows, the median defense weakens in high D.)\n")

    print("=" * 70)
    print("GAP 2: what does the FAIR-adversary boundary fit? (D=8, mean aggregation)")
    print("  measured f* vs the law 1/(1+rho); residual = measured - law")
    print("=" * 70)
    rhos = [0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.5]
    print("   rho    measured   1/(1+rho)   residual")
    resid = []
    for rho in rhos:
        m = statistics.mean(
            fstar(*make_world(s, 8), 8, w_decoy=rho, mode="mean", adv="fair") for s in seeds)
        law = 1.0 / (1.0 + rho)
        resid.append(m - law)
        print(f"   {rho:4.2f}    {m:.3f}      {law:.3f}      {m - law:+.3f}")
    print(f"\n  mean residual = {statistics.mean(resid):+.3f}  "
          f"(std {statistics.pstdev(resid):.3f})")
    # try a single additive-constant corrected law
    c = statistics.mean(resid)
    err_law = statistics.mean(abs(r) for r in resid)
    err_corr = statistics.mean(abs(r - c) for r in resid)
    print(f"  mean|err| law 1/(1+rho)         = {err_law:.3f}")
    print(f"  mean|err| corrected 1/(1+rho)+{c:+.2f} = {err_corr:.3f}")
    print("  (small, ~constant positive residual => the 'coverage bonus': honest agents")
    print("   share sight via consensus, so the commons tolerates slightly MORE than the")
    print("   bare depth law predicts. The law's FORM (falls with rho) is correct.)")


if __name__ == "__main__":
    main()
