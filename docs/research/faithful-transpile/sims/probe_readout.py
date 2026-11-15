"""A1 — carry the readout fix to its end: the canonical corrected numbers.

Proven wrong: every original sim reads the answer as _mean(agents) even in gated mode, so the
gate governs only the consensus TARGET, not the reported answer. Adjacent proven solution: read
the answer out with the same robust aggregator the gate uses. This produces the corrected
canonical tipping points and shows exactly when the old (mean-readout) numbers were safe and when
they were an illusion.

Three readout regimes x two adversary types:
  readout in {mean, median}  x  adversary in {bounded (natural, pulls toward decoy point q),
                                              unbounded (committed liar, drifts to an extreme)}
Stdlib, seeded, deterministic. Mirrors contested_aperture.py geometry (N=9).
"""
from __future__ import annotations
import math, random, statistics

D, N, STEPS, LR, K, SIGMA = 8, 9, 1200, 0.15, 0.30, 2.2


def _sub(a, b): return [x - y for x, y in zip(a, b)]
def _add(a, b): return [x + y for x, y in zip(a, b)]
def _scale(a, s): return [x * s for x in a]
def _dist(a, b): return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
def _mean(vs): return [sum(c) / len(vs) for c in zip(*vs)]
def _median(vs): return [statistics.median(c) for c in zip(*vs)]


def make_world(seed):
    rng = random.Random(seed)
    t = [rng.uniform(-1, 1) for _ in range(D)]
    q = _add(t, [rng.choice([-1, 1]) * 3.0 for _ in range(D)])
    masks = [[1 if rng.random() < 0.7 else 0 for _ in range(D)] for _ in range(N)]
    for j in range(D):
        if not any(masks[i][j] for i in range(N)):
            masks[rng.randrange(N)][j] = 1
    return t, q, masks


def well_grad(x, c, mask, w=1.0):
    d2 = sum((c[j] - x[j]) ** 2 for j in range(D))
    p = w * math.exp(-d2 / (2 * SIGMA ** 2))
    return [p * (c[j] - x[j]) * mask[j] for j in range(D)]


def run(t, q, masks, n_adv, *, target, readout, adv):
    rng = random.Random(99)
    mid = _mean([t, q])
    agents = [_add(mid, [rng.uniform(-1, 1) for _ in range(D)]) for _ in range(N)]
    advs = set(range(n_adv))
    sign = [1.0 if q[j] >= t[j] else -1.0 for j in range(D)]
    agg = {"mean": _mean, "median": _median}
    for _ in range(STEPS):
        bar = agg[target](agents)
        new = []
        for i, x in enumerate(agents):
            if i in advs:
                if adv == "bounded":
                    nx = _add(_add(x, _scale(_sub(q, x), LR)), _scale(_sub(bar, x), K))
                else:  # unbounded committed liar: steady drift to an extreme on the decoy side
                    nx = [x[j] + sign[j] * LR * 3.0 for j in range(D)]
                new.append(nx)
            else:
                v = _scale(well_grad(x, t, masks[i]), LR)
                new.append(_add(_add(x, v), _scale(_sub(bar, x), K)))
        agents = new
    bar = agg[readout](agents)
    return _dist(bar, t) < _dist(bar, q)


def fstar(t, q, masks, **kw):
    for n in range(N + 1):
        if not run(t, q, masks, n, **kw):
            return n / N
    return 1.0


def main():
    seeds = [7, 11, 19, 23, 31, 43]
    print("A1: corrected canonical tipping points f* (fraction of adversaries truth survives)\n")
    print("  target = aggregator used DURING dynamics; readout = aggregator for the FINAL answer\n")
    print("  adversary   target  readout    f*")
    combos = [
        ("bounded",   "mean",   "mean"),    # the original naive commons
        ("bounded",   "median", "mean"),    # original 'gate' (gate target, mean readout) -> the old 44%
        ("bounded",   "median", "median"),  # gate target AND readout (the fix)
        ("unbounded", "mean",   "mean"),    # naive vs a committed liar
        ("unbounded", "median", "mean"),    # gate target but mean readout -> the illusion breaks
        ("unbounded", "median", "median"),  # the fix: gate the readout too
    ]
    for adv, target, readout in combos:
        fs = statistics.mean(fstar(*make_world(s), target=target, readout=readout, adv=adv)
                             for s in seeds)
        tag = ""
        if (adv, target, readout) == ("bounded", "median", "mean"):
            tag = "  <- the old headline (looked robust)"
        if (adv, target, readout) == ("unbounded", "median", "mean"):
            tag = "  <- gate target, mean readout: COLLAPSES"
        if readout == "median" and target == "median":
            tag = "  <- corrected gate (target+readout)"
        print(f"  {adv:9s}   {target:6s}  {readout:6s}   {fs:.2f}{tag}")
    print("\n  READ: the gate's protection is real ONLY when the readout is also gated. Against a")
    print("  committed (unbounded) liar, gate-target + mean-readout breaks at ~1/N; gate the")
    print("  readout and tolerance returns to ~the median breakdown. Carry-to-end: report the")
    print("  (target+readout) row as canonical; the old mean-readout headline was bounded-adv-only.")


if __name__ == "__main__":
    main()
