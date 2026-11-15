"""PROBE A — is Q-A's "30/30 ownerless" an artifact of the start distribution?

contested_aperture.py Q-A seeds agents uniform(-5,5)^D. The truth t ~ uniform(-1,1)
sits near the origin; the decoy q = t +/- 3 per dim sits ~8.5 away. So the CENTROID
of the start cloud sits right on top of t, and the consensus pull (K) drags everyone
toward that centroid -> toward t -> the deep well captures them. The claim "reaches
truth from ANYWHERE / ownerless" may just be "the start cloud was centered on truth."

Test: hold the world and dynamics IDENTICAL to contested_aperture.py (good faith,
no adversaries), but SHIFT the center of the start cloud along the t->q axis from
t (alpha=0) to q (alpha=1) and beyond (alpha=1.5). Same per-agent jitter spread.
If ownerlessness is real, truth should still win for centers near/at the decoy.
If it collapses as the cloud moves onto q, the 30/30 was a start-distribution artifact.

Stdlib, seeded, deterministic. Mirrors contested_aperture.py constants exactly.
"""
from __future__ import annotations

import math
import random
import statistics

D = 8
N = 9
STEPS = 1200
LR = 0.15
K = 0.30
SIGMA = 2.2


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


def criterion_grad(x, t, q, mask, w_true=1.0, w_decoy=0.55):
    dt2 = sum((t[j] - x[j]) ** 2 for j in range(D))
    dq2 = sum((q[j] - x[j]) ** 2 for j in range(D))
    pt = w_true * math.exp(-dt2 / (2 * SIGMA ** 2))
    pq = w_decoy * math.exp(-dq2 / (2 * SIGMA ** 2))
    g = [pt * (t[j] - x[j]) + pq * (q[j] - x[j]) for j in range(D)]
    return [g[j] * mask[j] for j in range(D)]


def run(t, q, masks, starts):
    agents = [list(x) for x in starts]
    for _ in range(STEPS):
        bar = _mean(agents)
        new = []
        for i, x in enumerate(agents):
            upd = _add(x, _scale(criterion_grad(x, t, q, masks[i]), LR))
            upd = _add(upd, _scale(_sub(bar, x), K))
            new.append(upd)
        agents = new
    bar = _mean(agents)
    return _dist(bar, t), _dist(bar, q)


def main():
    print("PROBE A: Q-A ownerlessness vs start-cloud center (all good faith, no adversaries)")
    print("  Start cloud centered at  c = t + alpha*(q - t)  with the SAME jitter as Q-A.")
    print("  alpha=0 -> centered on truth; alpha=1 -> centered on the decoy.\n")
    print("  jitter   alpha   reached TRUE / 30   reached DECOY / 30   median err-to-truth")
    # Q-A used uniform(-5,5) jitter (half-width 5). Also test a tight cloud (half-width 1)
    # to isolate the center effect from the cloud being wide enough to straddle both wells.
    for half in (5.0, 1.0):
        for alpha in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5):
            reach_t = reach_q = 0
            errs = []
            for s in range(30):
                t, q, masks = make_world(7)  # same world as contested_aperture.py
                rng = random.Random(2000 + s)
                center = _add(t, _scale(_sub(q, t), alpha))
                starts = [_add(center, [rng.uniform(-half, half) for _ in range(D)])
                          for _ in range(N)]
                et, eq = run(t, q, masks, starts)
                errs.append(et)
                if et < 0.5:
                    reach_t += 1
                elif eq < 0.5:
                    reach_q += 1
            print(f"   {half:4.1f}    {alpha:4.2f}        {reach_t:2d}/30              "
                  f"{reach_q:2d}/30             {statistics.median(errs):.4f}")
        print()
    print("  READ: if TRUE-well count stays ~30/30 across alpha, ownerlessness is real.")
    print("  If it collapses as alpha->1 (cloud moves onto the decoy), the original 30/30")
    print("  rode on a start cloud that happened to be centered on truth.")


if __name__ == "__main__":
    main()
