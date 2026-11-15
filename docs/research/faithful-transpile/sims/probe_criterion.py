"""A4 — the criterion residue: can ANY internal statistic certify the well is truth?

The thesis's hardest claim: the system can hold itself on the line but cannot, from inside,
certify the line is the RIGHT one -- certification must come from outside the tube. This tests
it as an impossibility-within-the-model: build a MORE SEDUCTIVE decoy (deeper + wider basin than
the true well), let the good-faith commons converge, and measure whether internal observables
(spread, convergence speed, gradient residual, agent agreement) at the WRONG attractor look any
worse than at the right one. If internal 'confidence' is just as high (or higher) at the seductive
decoy as at truth, then no internal statistic separates truth from the best attractor -> the
residue is real (within the model). If some statistic reliably flags the wrong well, that would be
a candidate internal certifier (a surprising solution).

Stdlib, seeded, deterministic. Truth is defined ONLY by the external label (which well we call t).
"""
from __future__ import annotations
import math, random, statistics

D, N, STEPS, LR, K = 8, 9, 1500, 0.15, 0.30


def _sub(a, b): return [x - y for x, y in zip(a, b)]
def _add(a, b): return [x + y for x, y in zip(a, b)]
def _scale(a, s): return [x * s for x in a]
def _dist(a, b): return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
def _mean(vs): return [sum(c) / len(vs) for c in zip(*vs)]


def make_world(seed):
    rng = random.Random(seed)
    t = [rng.uniform(-1, 1) for _ in range(D)]
    q = _add(t, [rng.choice([-1, 1]) * 3.0 for _ in range(D)])
    masks = [[1 if rng.random() < 0.7 else 0 for _ in range(D)] for _ in range(N)]
    for j in range(D):
        if not any(masks[i][j] for i in range(N)):
            masks[rng.randrange(N)][j] = 1
    return t, q, masks


def grad(x, t, q, mask, w_t, s_t, w_q, s_q):
    dt2 = sum((t[j] - x[j]) ** 2 for j in range(D))
    dq2 = sum((q[j] - x[j]) ** 2 for j in range(D))
    pt = w_t * math.exp(-dt2 / (2 * s_t ** 2))
    pq = w_q * math.exp(-dq2 / (2 * s_q ** 2))
    return [(pt * (t[j] - x[j]) + pq * (q[j] - x[j])) * mask[j] for j in range(D)]


def converge(t, q, masks, start_c, params):
    rng = random.Random(123)
    agents = [_add(start_c, [rng.uniform(-1, 1) for _ in range(D)]) for _ in range(N)]
    traj = []
    for step in range(STEPS):
        bar = _mean(agents)
        traj.append(max(_dist(a, bar) for a in agents))   # spread over time (for speed)
        agents = [_add(_add(x, _scale(grad(x, t, q, masks[i], *params), LR)),
                       _scale(_sub(bar, x), K)) for i, x in enumerate(agents)]
    bar = _mean(agents)
    spread = max(_dist(a, bar) for a in agents)
    # convergence speed: steps to reach 10% of initial spread
    s0 = traj[0] or 1.0
    speed = next((i for i, s in enumerate(traj) if s < 0.1 * s0), STEPS)
    # gradient residual at rest (how strongly the criterion still pulls = "unsettledness")
    gres = statistics.mean(_dist(grad(a, t, q, masks[i], *params), [0] * D) for i, a in enumerate(agents))
    landed_t = _dist(bar, t) < _dist(bar, q)
    return landed_t, spread, speed, gres


def main():
    seeds = [7, 11, 19, 23, 31, 43]
    # TRUE well: depth 1.0, width 2.2.  SEDUCTIVE decoy: DEEPER (1.4) and WIDER (3.2).
    params = dict(w_t=1.0, s_t=2.2, w_q=1.4, s_q=3.2)
    print("A4: is the wrong (seductive) attractor internally distinguishable from the right one?")
    print(f"  true well: w=1.0 sigma=2.2 | decoy: w=1.4 sigma=3.2 (deeper+wider = more seductive)\n")
    print("  start    landed   spread    conv-speed(steps)   grad-residual")
    rows = {}
    for label, alpha in [("near truth", 0.0), ("near decoy", 1.0)]:
        ls, sp, spd, gr = [], [], [], []
        for s in seeds:
            t, q, masks = make_world(s)
            c = _add(t, _scale(_sub(q, t), alpha))
            landed_t, spread, speed, gres = converge(t, q, masks, c, tuple(params.values()))
            ls.append(landed_t); sp.append(spread); spd.append(speed); gr.append(gres)
        rows[label] = (sum(ls), statistics.mean(sp), statistics.mean(spd), statistics.mean(gr))
        well = "TRUTH" if sum(ls) > len(seeds) / 2 else "DECOY"
        print(f"  {label:10s} ->{well:6s} {statistics.mean(sp):.4f}   {statistics.mean(spd):8.1f}"
              f"          {statistics.mean(gr):.5f}   ({sum(ls)}/{len(seeds)} to truth)")
    print("\n  READ: if the run that lands in the DECOY shows spread / speed / residual just as")
    print("  good as (or better than) the run that lands in TRUTH, then internal 'confidence'")
    print("  does NOT track external correctness -> no internal certifier -> the residue is real")
    print("  within the model: the criterion that says which well is truth must come from OUTSIDE.")


if __name__ == "__main__":
    main()
