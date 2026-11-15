"""A2 — carry the ownerlessness disproof to its end: DERIVE the basin separatrix.

The "ownerless / reaches truth from anywhere" claim is a start-distribution artifact
(probe_ownerless.py). The honest replacement: which well wins is governed by a SEPARATRIX
in (start-position, decoy-depth) space. This finds it.

All good faith, no adversaries. Start cloud centered at c = t + alpha*(q - t).
For each decoy depth rho (= w_decoy / w_true), find alpha* = the start fraction at which
truth stops winning (the basin boundary). Then characterize alpha*(rho).

Prediction to test: alpha* falls as rho rises (a deeper decoy captures from closer to truth);
at rho=1 (equal depth) the separatrix should sit at alpha*~0.5 by symmetry. If that holds, the
replacement law is clean: truth wins iff the start is closer (in basin terms) to t than the
depth-weighted boundary -- a real governed boundary, not "ownerless".

Stdlib, seeded, deterministic. Dynamics mirror contested_aperture.py (good faith).
"""
from __future__ import annotations
import math, random, statistics

D, N, STEPS, LR, K, SIGMA = 8, 9, 1200, 0.15, 0.30, 2.2


def _sub(a, b): return [x - y for x, y in zip(a, b)]
def _add(a, b): return [x + y for x, y in zip(a, b)]
def _scale(a, s): return [x * s for x in a]
def _dist(a, b): return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
def _mean(vs): return [sum(c) / len(vs) for c in zip(*vs)]


def make_world(seed, rho):
    rng = random.Random(seed)
    t = [rng.uniform(-1, 1) for _ in range(D)]
    q = _add(t, [rng.choice([-1, 1]) * 3.0 for _ in range(D)])
    masks = [[1 if rng.random() < 0.7 else 0 for _ in range(D)] for _ in range(N)]
    for j in range(D):
        if not any(masks[i][j] for i in range(N)):
            masks[rng.randrange(N)][j] = 1
    return t, q, masks


def grad(x, t, q, mask, rho):
    dt2 = sum((t[j] - x[j]) ** 2 for j in range(D))
    dq2 = sum((q[j] - x[j]) ** 2 for j in range(D))
    pt = 1.0 * math.exp(-dt2 / (2 * SIGMA ** 2))
    pq = rho * math.exp(-dq2 / (2 * SIGMA ** 2))
    return [(pt * (t[j] - x[j]) + pq * (q[j] - x[j])) * mask[j] for j in range(D)]


def truth_win_frac(rho, alpha, seeds, half=1.0):
    wins = 0
    tot = 0
    for s in seeds:
        t, q, masks = make_world(s, rho)
        rng = random.Random(5000 + s)
        center = _add(t, _scale(_sub(q, t), alpha))
        agents = [_add(center, [rng.uniform(-half, half) for _ in range(D)]) for _ in range(N)]
        for _ in range(STEPS):
            bar = _mean(agents)
            agents = [_add(_add(x, _scale(grad(x, t, q, masks[i], rho), LR)),
                           _scale(_sub(bar, x), K)) for i, x in enumerate(agents)]
        bar = _mean(agents)
        wins += (_dist(bar, t) < _dist(bar, q))
        tot += 1
    return wins / tot


def find_alpha_star(rho, seeds):
    """Bisect alpha in [0,1] for the 50% truth-win crossing."""
    lo, hi = 0.0, 1.0
    if truth_win_frac(rho, lo, seeds) < 0.5:
        return 0.0
    if truth_win_frac(rho, hi, seeds) >= 0.5:
        return 1.0
    for _ in range(12):
        mid = (lo + hi) / 2
        if truth_win_frac(rho, mid, seeds) >= 0.5:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main():
    seeds = [7, 11, 19, 23, 31, 43, 2, 5]
    print("A2: basin separatrix alpha*(rho) — the honest replacement for 'ownerless'")
    print("  alpha* = start fraction (t->q) at which truth stops winning. all good faith.\n")
    print("   rho    alpha*    interpretation")
    for rho in (0.4, 0.55, 0.7, 0.85, 1.0, 1.2):
        a = find_alpha_star(rho, seeds)
        note = ("truth wins even from the decoy" if a >= 0.99 else
                "truth never wins" if a <= 0.01 else f"truth wins if start < {a:.2f} of the way to q")
        print(f"   {rho:4.2f}   {a:5.2f}     {note}")
    print("\n  READ: a monotone alpha*(rho) that falls as rho rises = a clean governed boundary")
    print("  (deeper decoy captures from closer in). alpha*~0.5 at rho=1 = depth symmetry.")
    print("  That boundary IS the replacement claim: not 'ownerless', but 'truth wins inside")
    print("  its depth-weighted basin' — path-dependence governed by depth vs start.")


if __name__ == "__main__":
    main()
