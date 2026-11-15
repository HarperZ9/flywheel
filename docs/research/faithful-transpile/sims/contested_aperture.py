"""The CONTESTED aperture — the hard case, where the thesis can actually break.

Sim 1 (reconcile_dynamics.py) tested a convex world: one truth, all agents in good faith.
It held — but a convex world GUARANTEES one attractor and exact convergence, so the clean
result was partly baked in. Truth rises from the hard case. Two ways the aperture can fall:

  Q-A  NON-CONVEX criterion: a deep TRUE well at t and a shallow DECOY well at q.
       Now starting position matters. Is the commons still OWNERLESS (everyone reaches t),
       or does it fragment into basins (path-DEPENDENT — a partial refutation)?
       And: does reconciliation RESCUE agents stuck in the decoy, or not?

  Q-B  ADVERSARIES: a fraction f of agents are bad-faith — they ignore the criterion and
       pull everyone toward the decoy while still sitting in the commons (dragging the mean).
       At what f does the place of peace become a battleground? Is there a tolerance threshold?

The thesis does NOT predict "always wins." It predicts the regime is GOVERNED: peace holds
while the unauthored criterion is strong enough AND the bad-faith fraction stays below a bound.
This sim measures that bound. Stdlib only, seeded, deterministic.
"""
from __future__ import annotations

import math
import random
import statistics

D = 8
N = 9
STEPS = 1200
LR = 0.15      # criterion pull
K = 0.30       # consensus pull
SIGMA = 2.2    # basin width


def _sub(a, b): return [x - y for x, y in zip(a, b)]
def _add(a, b): return [x + y for x, y in zip(a, b)]
def _scale(a, s): return [x * s for x in a]
def _dist(a, b): return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
def _mean(vs): return [sum(c) / len(vs) for c in zip(*vs)]


def make_world(seed):
    rng = random.Random(seed)
    t = [rng.uniform(-1, 1) for _ in range(D)]              # the TRUE well (deep)
    q = _add(t, [rng.choice([-1, 1]) * 3.0 for _ in range(D)])  # DECOY well, offset away
    masks = []
    for _ in range(N):
        masks.append([1 if rng.random() < 0.7 else 0 for _ in range(D)])
    for j in range(D):
        if not any(masks[i][j] for i in range(N)):
            masks[rng.randrange(N)][j] = 1
    return t, q, masks


def criterion_grad(x, t, q, mask, w_true=1.0, w_decoy=0.55):
    """Nonlinear field: two inverted-Gaussian wells. Deep TRUE well + shallow DECOY well.
    Agent sees only its masked dims. Gradient pulls toward whichever well dominates locally."""
    dt2 = sum((t[j] - x[j]) ** 2 for j in range(D))
    dq2 = sum((q[j] - x[j]) ** 2 for j in range(D))
    pt = w_true * math.exp(-dt2 / (2 * SIGMA ** 2))
    pq = w_decoy * math.exp(-dq2 / (2 * SIGMA ** 2))
    g = [pt * (t[j] - x[j]) + pq * (q[j] - x[j]) for j in range(D)]
    return [g[j] * mask[j] for j in range(D)]


def _median_point(vs):
    """Coordinate-wise median — a robust center that rejects outlier pulls (the GATE)."""
    return [statistics.median(col) for col in zip(*vs)]


def run(t, q, masks, starts, *, n_adv=0, robust=False):
    """Honest agents ascend the masked criterion; adversaries pull toward the decoy q.
    Consensus target = mean (naive commons) or coordinate-wise median (gated commons)."""
    agents = [list(x) for x in starts]
    adv = set(range(n_adv))                        # first n_adv agents are bad-faith
    for _ in range(STEPS):
        bar = _median_point(agents) if robust else _mean(agents)
        new = []
        for i, x in enumerate(agents):
            upd = list(x)
            if i in adv:
                upd = _add(upd, _scale(_sub(q, x), LR))     # bad faith: drive toward decoy
            else:
                upd = _add(upd, _scale(criterion_grad(x, t, q, masks[i]), LR))
            upd = _add(upd, _scale(_sub(bar, x), K))         # everyone reconciles to the center
            new.append(upd)
        agents = new
    bar = _mean(agents)
    return bar, _dist(bar, t), _dist(bar, q)


def main():
    t, q, masks = make_world(seed=7)
    print(f"world: d={D}, agents={N}, sigma={SIGMA}, ||t-q||={_dist(t, q):.3f} (true vs decoy)")
    print(f"decoy weight 0.55 of true (shallower). lr={LR}, k={K}\n")

    # Q-A : non-convex, all good faith. Many seeds — does everyone reach t, or split basins?
    print("Q-A  ownerless under non-convexity? (all good faith, 30 random seed sets)")
    reach_t = reach_q = other = 0
    errs = []
    for s in range(30):
        rng = random.Random(2000 + s)
        # seed agents anywhere — some near the decoy, some near truth, some far
        starts = [[rng.uniform(-5, 5) for _ in range(D)] for _ in range(N)]
        _, et, eq = run(t, q, masks, starts)
        errs.append(et)
        if et < 0.5:
            reach_t += 1
        elif eq < 0.5:
            reach_q += 1
        else:
            other += 1
    print(f"   reached TRUE well: {reach_t}/30   decoy: {reach_q}/30   neither: {other}/30")
    print(f"   median error-to-truth: {statistics.median(errs):.4f}")
    verdict = ("ownerless (one basin wins)" if reach_t >= 28 else
               "PATH-DEPENDENT (basins fragment) — partial refutation" if reach_q + other > 2 else
               "mostly ownerless")
    print(f"   -> {verdict}\n")

    # Q-B : adversary sweep — naive (mean) commons vs gated (median) commons.
    print("Q-B  adversarial tolerance — does a GATE (robust aggregation) hold the peace longer?")
    print("   adversaries   naive-mean -> truth?    gated-median -> truth?")
    thr = {"naive": None, "gated": None}
    for n_adv in range(0, N):
        rng = random.Random(99)
        mid = _mean([t, q])
        starts = [_add(mid, [rng.uniform(-1, 1) for _ in range(D)]) for _ in range(N)]
        _, et_m, eq_m = run(t, q, masks, starts, n_adv=n_adv, robust=False)
        _, et_g, eq_g = run(t, q, masks, starts, n_adv=n_adv, robust=True)
        win_m = et_m < eq_m
        win_g = et_g < eq_g
        if thr["naive"] is None and not win_m:
            thr["naive"] = n_adv
        if thr["gated"] is None and not win_g:
            thr["gated"] = n_adv
        tag = lambda w, e: ("COMMONS" if w else "battleground") + f" ({e:6.3f})"
        print(f"      {n_adv}/{N}={n_adv/N:4.2f}   {tag(win_m, et_m):24s}  {tag(win_g, et_g)}")
    print()
    for k, v in thr.items():
        msg = (f"{v}/{N} ({v/N:.0%})" if v is not None else "never overrun")
        print(f"   {k:6s} commons tipping point: {msg}")
    print("   -> the gate (criterion-on-the-line) is what buys back the tolerance the")
    print("      naive average gives away. Same aperture; the membrane sets the bound.")


if __name__ == "__main__":
    main()
