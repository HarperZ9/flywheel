"""Map the boundary — turn the two tipping points into a phase surface, and test the law.

Sim 2 gave two numbers: naive commons falls at 22% bad faith, gated at 44% (for one decoy depth).
This sweeps the whole plane: adversary fraction f  x  decoy depth ratio rho = w_decoy/w_true.
For every cell, run the dynamics and record the regime (commons=truth vs battleground=decoy),
for BOTH naive-mean and gated-median aggregation.

Then test the conjectured law from the thesis:
    peace holds iff  criterion_depth * honest_fraction  >  decoy_depth * bad_fraction
i.e. naive prediction  f* = 1/(1+rho).  Does the measured boundary match it? If not, the
boundary is DYNAMICAL/GEOMETRIC (set by where consensus parks), not a static depth*fraction
algebra — an honest finding either way. A second basin width (sigma) checks that.

Stdlib only, seeded, deterministic. The map is the deliverable.
"""
from __future__ import annotations

import math
import random
import statistics

D = 8
N = 20          # finer fraction resolution
STEPS = 1000
LR = 0.15
K = 0.30
SEP = 3.0       # per-dim offset of decoy from truth -> ||t-q|| = SEP*sqrt(D)


def _sub(a, b): return [x - y for x, y in zip(a, b)]
def _add(a, b): return [x + y for x, y in zip(a, b)]
def _scale(a, s): return [x * s for x in a]
def _dist(a, b): return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
def _mean(vs): return [sum(c) / len(vs) for c in zip(*vs)]
def _median(vs): return [statistics.median(c) for c in zip(*vs)]


def make_world(seed):
    rng = random.Random(seed)
    t = [rng.uniform(-1, 1) for _ in range(D)]
    q = _add(t, [rng.choice([-1, 1]) * SEP for _ in range(D)])
    masks = []
    for _ in range(N):
        masks.append([1 if rng.random() < 0.7 else 0 for _ in range(D)])
    for j in range(D):
        if not any(masks[i][j] for i in range(N)):
            masks[rng.randrange(N)][j] = 1
    return t, q, masks


def grad(x, t, q, mask, sigma, w_true, w_decoy):
    dt2 = sum((t[j] - x[j]) ** 2 for j in range(D))
    dq2 = sum((q[j] - x[j]) ** 2 for j in range(D))
    pt = w_true * math.exp(-dt2 / (2 * sigma ** 2))
    pq = w_decoy * math.exp(-dq2 / (2 * sigma ** 2))
    return [(pt * (t[j] - x[j]) + pq * (q[j] - x[j])) * mask[j] for j in range(D)]


def reaches_truth(t, q, masks, n_adv, *, sigma, w_decoy, robust):
    rng = random.Random(99)
    mid = _mean([t, q])
    agents = [_add(mid, [rng.uniform(-1, 1) for _ in range(D)]) for _ in range(N)]
    adv = set(range(n_adv))
    for _ in range(STEPS):
        bar = _median(agents) if robust else _mean(agents)
        new = []
        for i, x in enumerate(agents):
            if i in adv:
                upd = _add(x, _scale(_sub(q, x), LR))
            else:
                upd = _add(x, _scale(grad(x, t, q, masks[i], sigma, 1.0, w_decoy), LR))
            new.append(_add(upd, _scale(_sub(bar, x), K)))
        agents = new
    bar = _mean(agents)
    return _dist(bar, t) < _dist(bar, q)


def boundary(t, q, masks, *, sigma, w_decoy, robust):
    """Smallest adversary fraction at which peace falls (None = never falls in range)."""
    for n in range(N):
        if not reaches_truth(t, q, masks, n, sigma=sigma, w_decoy=w_decoy, robust=robust):
            return n / N
    return None


def phase_map(t, q, masks, *, sigma, robust, rhos, fracs):
    print(f"   sigma={sigma}  aggregation={'GATED (median)' if robust else 'naive (mean)'}")
    print("   rho\\f " + "".join(f"{f:5.2f}" for f in fracs))
    for rho in rhos:
        row = []
        for f in fracs:
            n = round(f * N)
            ok = reaches_truth(t, q, masks, n, sigma=sigma, w_decoy=rho, robust=robust)
            row.append("  #  " if ok else "  .  ")
        print(f"   {rho:4.2f} " + "".join(row))
    print("        # = COMMONS (truth)    . = battleground (decoy)\n")


def main():
    t, q, masks = make_world(seed=7)
    sigma0 = 2.2
    print(f"world: d={D}, agents={N}, ||t-q||={_dist(t, q):.2f}, lr={LR}, k={K}\n")

    rhos = [0.2, 0.4, 0.6, 0.8, 1.0, 1.2]
    fracs = [0.0, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]

    print("PHASE MAP — adversary fraction (f) x decoy depth (rho):\n")
    phase_map(t, q, masks, sigma=sigma0, robust=False, rhos=rhos, fracs=fracs)
    phase_map(t, q, masks, sigma=sigma0, robust=True, rhos=rhos, fracs=fracs)

    print("BOUNDARY vs the conjectured law  f* = 1/(1+rho)  (static depth*fraction):")
    print("   rho   measured naive   measured gated   law 1/(1+rho)")
    for rho in rhos:
        bn = boundary(t, q, masks, sigma=sigma0, w_decoy=rho, robust=False)
        bg = boundary(t, q, masks, sigma=sigma0, w_decoy=rho, robust=True)
        law = 1.0 / (1.0 + rho)
        sn = f"{bn:.2f}" if bn is not None else " >.5"
        sg = f"{bg:.2f}" if bg is not None else " >.5"
        print(f"   {rho:4.2f}      {sn:>6}          {sg:>6}          {law:.2f}")

    print("\nGEOMETRY check — same plane, WIDER basins (sigma 2.2 -> 3.5):")
    print("   rho   naive f*(2.2)   naive f*(3.5)")
    for rho in rhos:
        b1 = boundary(t, q, masks, sigma=2.2, w_decoy=rho, robust=False)
        b2 = boundary(t, q, masks, sigma=3.5, w_decoy=rho, robust=False)
        s1 = f"{b1:.2f}" if b1 is not None else " >.5"
        s2 = f"{b2:.2f}" if b2 is not None else " >.5"
        print(f"   {rho:4.2f}      {s1:>6}         {s2:>6}")
    print("\n   If f* moves with sigma at fixed rho, the boundary is DYNAMICAL/geometric,")
    print("   not a static depth*fraction law. The gate columns show how far it shifts out.")


if __name__ == "__main__":
    main()
