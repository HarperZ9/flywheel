"""PROBE B — the coordinate-decomposed worst-case attack on the median gate.

The handoff's open question #2: the gate (coordinate-wise median) survives the NATURAL
coordinated attack (all adversaries pull toward the one decoy point q). But coordinate-wise
median has a known high-D weakness: each coordinate's median can be nudged independently,
and small per-axis nudges accumulate in QUADRATURE over D axes into a large Euclidean
displacement. A worst-case attacker decomposes by coordinate instead of aiming at q.

Two adversary models compared against the natural one:
  natural   : pull toward the decoy POINT q (the handoff's attack)
  decomposed: on EACH axis independently, shove that axis hard toward the q side, so the
              per-coordinate median is dragged as far as the adversary count allows. This
              is the attack coordinate-wise median is theoretically weakest against.
  extreme   : adversaries jump to a far extreme on the q side every step (max leverage on
              the median's ordering, ignoring their own field entirely).

We measure f* (tipping fraction) for mean vs median vs trimmed, across dimension, geometry
held constant (||t-q|| = S for all D, as in run_gaps.py). If the decomposed/extreme attack
drives the median's f* down toward (or below) the mean's, the gate's edge is NOT robust to
a purpose-built adversary, and "the gate holds" is overclaimed. If the median still holds
near its ~0.5 per-coordinate breakdown, the gate survives even the attack built to beat it.

Stdlib, seeded, deterministic. Constants mirror run_gaps.py.
"""
from __future__ import annotations

import math
import random
import statistics

N = 12
STEPS = 400
LR = 0.15
K = 0.30
S = 8.485
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
    off = S / math.sqrt(D)
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


def run(t, q, masks, n_adv, D, *, mode, adv):
    rng = random.Random(99)
    mid = _mean([t, q])
    agents = [_add(mid, [rng.uniform(-1, 1) for _ in range(D)]) for _ in range(N)]
    advs = set(range(n_adv))
    # per-axis sign of the decoy direction (q is on this side of t on each axis)
    sign = [1.0 if q[j] >= t[j] else -1.0 for j in range(D)]
    BIG = 10.0 * S  # extreme leverage magnitude
    for _ in range(STEPS):
        bar = agg(agents, mode)
        new = []
        for i, x in enumerate(agents):
            if i in advs:
                if adv == "natural":
                    nx = _add(_add(x, _scale(_sub(q, x), LR)), _scale(_sub(bar, x), K))
                elif adv == "decomposed":
                    # shove each axis hard toward the q side, independent of the q point.
                    # adversary ignores consensus pull (committed liar) to maximize median drag.
                    nx = [x[j] + sign[j] * LR * S for j in range(D)]
                elif adv == "extreme":
                    # teleport to a far extreme on the q side every step: maximal ordering leverage
                    nx = [t[j] + sign[j] * BIG for j in range(D)]
                else:
                    nx = list(x)
            else:
                v = _scale(well_grad(x, t, masks[i], 1.0, D), LR)
                nx = _add(_add(x, v), _scale(_sub(bar, x), K))
            new.append(nx)
        agents = new
    # FAIR readout: read the answer with the SAME aggregator the gate uses. Reading the
    # gated system out as a raw mean lets any unbounded adversary corrupt the answer even
    # though the gate rejected it during the dynamics -- that tests the readout, not the gate.
    bar = agg(agents, mode)
    return _dist(bar, t) < _dist(bar, q)


def fstar(t, q, masks, D, **kw):
    for n in range(N + 1):
        if not run(t, q, masks, n, D, **kw):
            return n / N
    return 1.0


def main():
    seeds = [7, 11, 19, 23]
    print("PROBE B: does the median gate survive an attack BUILT to beat coordinate-wise median?")
    print("  f* (mean over seeds). Higher = more adversaries tolerated before truth loses.")
    print("  Compares the natural attack (handoff) to coordinate-decomposed & extreme attacks.\n")
    for adv in ("natural", "decomposed", "extreme"):
        print(f"  === adversary = {adv} ===")
        print("    D     mean     median    trimmed    gate gain (median-mean)")
        for D in (2, 8, 32, 64):
            res = {}
            for mode in ("mean", "median", "trimmed"):
                res[mode] = statistics.mean(
                    fstar(*make_world(s, D), D, mode=mode, adv=adv) for s in seeds)
            print(f"   {D:3d}    {res['mean']:.2f}     {res['median']:.2f}      "
                  f"{res['trimmed']:.2f}       {res['median'] - res['mean']:+.2f}")
        print()
    print("  READ: if 'gate gain' for decomposed/extreme stays clearly positive and flat in D,")
    print("  the gate survives the purpose-built attack. If it collapses to ~0 (or the median's")
    print("  f* falls toward the mean's) as D grows, the gate's edge is an artifact of the")
    print("  natural attack and 'the gate holds' is overclaimed for the worst case.")


if __name__ == "__main__":
    main()
