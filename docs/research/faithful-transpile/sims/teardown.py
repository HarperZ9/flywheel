"""Teardown — attack our own results until they break or survive. No mercy.

The headline claims to falsify:
  C1  "the endpoint exceeds the points" (commons recovers truth no agent can see)
  C2  "the gate doubles/triples adversary tolerance"
  C3  "the boundary is DYNAMICAL/GEOMETRIC (sigma-dependent), refuting f*=1/(1+rho)"
  C4  "felt-at-the-line, not depth, governs"

Prime suspect: C3/C4 may be ARTIFACTS of an unphysical adversary. Our adversary pulls toward
the decoy at FULL lever strength (undamped), while honest agents follow the criterion field
(Gaussian-damped, weak at the seam). A FAIR adversary is a wrong-but-sincere agent: it should
feel its own decoy field with the SAME distance damping. If we model it fairly, the sigma factor
cancels at the seam and the boundary should collapse back to f*=1/(1+rho) — refuting our refutation.

Also attacked: adversary coordination, adaptive worst-case attack, multi-seed cherry-picking,
aggregator-shopping, start dependence. Stdlib, seeded, deterministic.
"""
from __future__ import annotations

import math
import random
import statistics

D = 8
N = 12
STEPS = 500
LR = 0.15
K = 0.30
SEP = 3.0


def _sub(a, b): return [x - y for x, y in zip(a, b)]
def _add(a, b): return [x + y for x, y in zip(a, b)]
def _scale(a, s): return [x * s for x in a]
def _norm(a): return math.sqrt(sum(v * v for v in a))
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


def make_world(seed):
    rng = random.Random(seed)
    t = [rng.uniform(-1, 1) for _ in range(D)]
    q = _add(t, [rng.choice([-1, 1]) * SEP for _ in range(D)])
    masks = [[1 if rng.random() < 0.7 else 0 for _ in range(D)] for _ in range(N)]
    for j in range(D):
        if not any(masks[i][j] for i in range(N)):
            masks[rng.randrange(N)][j] = 1
    return t, q, masks


def well_grad(x, c, mask, sigma, w):
    d2 = sum((c[j] - x[j]) ** 2 for j in range(D))
    p = w * math.exp(-d2 / (2 * sigma ** 2))
    return [p * (c[j] - x[j]) * mask[j] for j in range(D)]


def run(t, q, masks, n_adv, *, sigma, w_decoy, mode="mean", adv="undamped", start="mid", seed=99):
    rng = random.Random(seed)
    if start == "mid":
        base = _mean([t, q])
    elif start == "truth":
        base = list(t)
    elif start == "decoy":
        base = list(q)
    else:  # dispersed
        base = None
    if base is None:
        agents = [[rng.uniform(-5, 5) for _ in range(D)] for _ in range(N)]
    else:
        agents = [_add(base, [rng.uniform(-1, 1) for _ in range(D)]) for _ in range(N)]
    advs = set(range(n_adv))
    full = [1] * D
    for _ in range(STEPS):
        bar = agg(agents, mode)
        new = []
        for i, x in enumerate(agents):
            if i in advs:
                if adv == "undamped":                      # full-lever pull to decoy (our original)
                    v = _scale(_sub(q, x), LR)
                elif adv == "fair":                        # wrong-but-sincere: decoy field, masked, damped
                    v = _scale(well_grad(x, q, masks[i], sigma, w_decoy), LR)
                elif adv == "fair_fullsight":              # sincere but fully-sighted (stronger fair)
                    v = _scale(well_grad(x, q, full, sigma, w_decoy), LR)
                elif adv == "adaptive":                    # worst-case: shove the mean away from truth
                    dirn = _sub(bar, t)
                    n = _norm(dirn) or 1.0
                    v = _scale(dirn, LR * SEP / n)
                elif adv == "random":                      # uncoordinated: each a fixed random heading
                    r = random.Random(seed * 100 + i)
                    dirn = [r.uniform(-1, 1) for _ in range(D)]
                    n = _norm(dirn) or 1.0
                    v = _scale(dirn, LR * SEP / n)
                else:
                    v = [0] * D
            else:
                v = _scale(well_grad(x, t, masks[i], sigma, 1.0), LR)
            new.append(_add(_add(x, v), _scale(_sub(bar, x), K)))
        agents = new
    bar = _mean(agents)
    return _dist(bar, t) < _dist(bar, q), _dist(bar, t)


def fstar(t, q, masks, **kw):
    for n in range(N + 1):
        ok, _ = run(t, q, masks, n, **kw)
        if not ok:
            return n / N
    return 1.0


def main():
    seeds = [7, 11, 19, 23, 31, 43]
    rhos = [0.3, 0.6, 1.0]

    print("=" * 74)
    print("ATTACK 1 (the crux): is the sigma-dependent boundary an artifact of an")
    print("unphysical (undamped) adversary? Fair adversary should restore f*=1/(1+rho).")
    print("=" * 74)
    print("  Each f* = mean over", len(seeds), "world seeds.  law = 1/(1+rho)\n")
    print("  rho   law   UNDAMPED s=2.2  UNDAMPED s=3.5   FAIR s=2.2  FAIR s=3.5")
    for rho in rhos:
        def avg(**kw):
            return statistics.mean(fstar(*make_world(s), w_decoy=rho, **kw) for s in seeds)
        u22 = avg(sigma=2.2, adv="undamped")
        u35 = avg(sigma=3.5, adv="undamped")
        f22 = avg(sigma=2.2, adv="fair")
        f35 = avg(sigma=3.5, adv="fair")
        print(f"  {rho:3.1f}  {1/(1+rho):.2f}     {u22:.2f}          {u35:.2f}"
              f"           {f22:.2f}        {f35:.2f}")
    print("\n  READ: if UNDAMPED moves with sigma but FAIR does not (and FAIR ~ law),")
    print("  then C3/C4 were artifacts of the unbounded adversary — the law survives for")
    print("  sincere adversaries; the geometric boundary is the signature of a LOUD one.\n")

    print("=" * 74)
    print("ATTACK 2: adversary coordination & worst-case. Coordinated should be worse")
    print("than random; adaptive should be worst of all. (undamped family, s=2.2, rho=0.6)")
    print("=" * 74)
    for label, kw in [("coordinated->decoy", dict(adv="undamped")),
                      ("uncoordinated/random", dict(adv="random")),
                      ("adaptive worst-case", dict(adv="adaptive"))]:
        fs = statistics.mean(fstar(*make_world(s), sigma=2.2, w_decoy=0.6, **kw) for s in seeds)
        print(f"  {label:22s} mean f* = {fs:.2f}")
    print("  (random/uncoordinated adversaries partly cancel -> expect HIGHER f*; we test")
    print("   the worst cases here, so real-world tolerance should sit at or above these.)\n")

    print("=" * 74)
    print("ATTACK 3: aggregator-shopping — is 'the gate' real, or did we pick a winner?")
    print("  f* for each aggregator (undamped adv, s=2.2, rho=0.6, mean over seeds)")
    print("=" * 74)
    for mode in ("mean", "median", "trimmed"):
        fs = statistics.mean(fstar(*make_world(s), sigma=2.2, w_decoy=0.6, mode=mode) for s in seeds)
        print(f"  {mode:8s} f* = {fs:.2f}")
    print("  (if median AND trimmed both beat mean, the win is 'robust aggregation' in")
    print("   general, not a median-specific fluke.)\n")

    print("=" * 74)
    print("ATTACK 4: start dependence — does the commons only work from a kind start?")
    print("  f* by initial condition (undamped adv, median gate, s=2.2, rho=0.6)")
    print("=" * 74)
    for st in ("truth", "mid", "decoy", "dispersed"):
        fs = statistics.mean(fstar(*make_world(s), sigma=2.2, w_decoy=0.6, mode="median",
                                   start=st, seed=99) for s in seeds)
        print(f"  start={st:10s} f* = {fs:.2f}")
    print("\n  (heavy start-dependence would mean the result rides on a favorable prior.)")


if __name__ == "__main__":
    main()
