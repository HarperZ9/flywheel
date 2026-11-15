"""The aperture as a reconciliation dynamical system — an arithmetic test of the thesis.

Thesis (operator, 2026-06-23): the answer is the fixed point where many independent,
mutually-distrusting constructions reconcile against a criterion NEITHER of them authored.
The place of peace and the battleground are the SAME place; only the criterion on the line
between (the membrane) decides whether the aperture is a big bang (truth) or a black hole
(collapse to nothing).

This file turns that into something arithmetic can adjudicate — and could falsify.

Setup (the honest, non-rigged part):
  - A truth vector t in R^d. It is the CRITERION. No agent authors it; it is the environment.
  - N agents, each starting at a random point (independent constructions).
  - Each agent is BLIND on a subset of dimensions: it cannot see the criterion gradient there.
    No single agent can reach t alone. The union of all agents' sight covers every dimension,
    so the truth is reachable ONLY by reconciliation, never by one mind.

Regimes (vary ONLY the governance term; the locus/system is identical):
  COMMONS      : consensus pull + each agent's PARTIAL criterion gradient.   (criterion ON)
  VOID         : consensus pull, NO criterion.                              (criterion OFF)
  BATTLEGROUND : pull toward one dominant agent, NO criterion.             (criterion OFF, authored)
  SOLO         : criterion only, NO consensus (each mind alone).           (the single point)

Predictions the sim could refute:
  P1  COMMONS reaches t (low error) — and beats SOLO (endpoint exceeds every point).
  P2  VOID converges but to the centroid — truth-blind (everything -> nothing).
  P3  BATTLEGROUND collapses to the dominant's blind answer (no shared truth).
  P4  Sweeping ONLY the criterion strength flips COMMONS<->VOID (same place, two regimes).
  P5  COMMONS is ownerless: many seed sets reach the SAME fixed point (tiny variance).

Stdlib only. Deterministic (seeded). The code is the argument; read the arithmetic.
"""
from __future__ import annotations

import math
import random
import statistics

D = 12          # dimensions of the representation space
N = 6           # number of agents (independent constructions)
STEPS = 800
LR = 0.12       # criterion (truth) pull strength
K = 0.30        # consensus (reconciliation) pull strength


def _vec_sub(a, b): return [x - y for x, y in zip(a, b)]
def _vec_add(a, b): return [x + y for x, y in zip(a, b)]
def _scale(a, s):   return [x * s for x in a]
def _dist(a, b):    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
def _mean(vs):      return [sum(col) / len(vs) for col in zip(*vs)]


def make_world(seed: int):
    """Truth vector + per-agent blind masks whose UNION covers every dimension."""
    rng = random.Random(seed)
    t = [rng.uniform(-1, 1) for _ in range(D)]
    # each agent sees a random ~2/3 of dimensions; then guarantee full coverage.
    masks = []
    for _ in range(N):
        masks.append([1 if rng.random() < 0.66 else 0 for _ in range(D)])
    for j in range(D):                       # ensure every dim is seen by >=1 agent
        if not any(masks[i][j] for i in range(N)):
            masks[rng.randrange(N)][j] = 1
    return t, masks, rng


def make_starts(rng):
    return [[rng.uniform(-3, 3) for _ in range(D)] for _ in range(N)]


def grad_to_truth(x, t, mask):
    """Partial criterion gradient: only the dims this agent can SEE (1 in mask)."""
    g = _vec_sub(t, x)                        # points toward truth
    return [g[j] * mask[j] for j in range(D)]


def step(agents, t, masks, *, criterion: bool, consensus: str):
    bar = _mean(agents)
    new = []
    for i, x in enumerate(agents):
        upd = list(x)
        if criterion:
            upd = _vec_add(upd, _scale(grad_to_truth(x, t, masks[i]), LR))
        if consensus == "mean":              # reconcile toward the shared center
            upd = _vec_add(upd, _scale(_vec_sub(bar, x), K))
        elif consensus == "dominant":        # pull toward agent 0 (authored, egocentric)
            upd = _vec_add(upd, _scale(_vec_sub(agents[0], x), K))
        new.append(upd)
    return new


def run(t, masks, starts, *, criterion, consensus):
    agents = [list(x) for x in starts]
    for _ in range(STEPS):
        agents = step(agents, t, masks, criterion=criterion, consensus=consensus)
    bar = _mean(agents)
    spread = max(_dist(a, bar) for a in agents)       # 0 => converged to one point
    err = _dist(bar, t)                                # distance of the answer to truth
    return bar, err, spread


def best_solo_error(t, masks, starts):
    """Each mind alone (criterion only, no consensus) — the best any single point reaches."""
    errs = []
    for i in range(N):
        a = list(starts[i])
        for _ in range(STEPS):
            a = _vec_add(a, _scale(grad_to_truth(a, t, masks[i]), LR))
        errs.append(_dist(a, t))
    return min(errs), statistics.mean(errs)


def main():
    global LR
    t, masks, rng = make_world(seed=42)
    starts = make_starts(rng)

    print(f"world: d={D}, agents={N}, steps={STEPS}, lr={LR}, k={K}")
    cover = [sum(masks[i][j] for i in range(N)) for j in range(D)]
    print(f"criterion visibility per dim (agents seeing it): {cover}  (min={min(cover)})")
    print()

    solo_best, solo_mean = best_solo_error(t, masks, starts)
    _, err_commons, spr_c = run(t, masks, starts, criterion=True, consensus="mean")
    _, err_void, spr_v = run(t, masks, starts, criterion=False, consensus="mean")
    _, err_battle, spr_b = run(t, masks, starts, criterion=False, consensus="dominant")

    print("REGIME              error-to-truth   spread   verdict")
    print(f"SOLO  (best single)   {solo_best:8.4f}        --     the best any one point reaches")
    print(f"SOLO  (mean single)   {solo_mean:8.4f}        --")
    print(f"COMMONS               {err_commons:8.4f}   {spr_c:7.4f}   P1: criterion + reconcile")
    print(f"VOID  (no criterion)  {err_void:8.4f}   {spr_v:7.4f}   P2: consensus, truth-blind")
    print(f"BATTLE (dominant)     {err_battle:8.4f}   {spr_b:7.4f}   P3: collapse to authored")
    print()
    print(f"P1 endpoint exceeds points?  COMMONS {err_commons:.4f} < best SOLO {solo_best:.4f}"
          f"  -> {'YES' if err_commons < solo_best else 'NO'}")
    print(f"P2 VOID is truth-blind?      VOID {err_void:.4f} ~ much worse than COMMONS"
          f"  -> {'YES' if err_void > 3 * err_commons + 1e-9 else 'NO'}")
    print(f"P3 BATTLE finds no truth?    BATTLE {err_battle:.4f} >> COMMONS"
          f"  -> {'YES' if err_battle > 3 * err_commons + 1e-9 else 'NO'}")

    # P4 — unity: hold the system fixed, sweep ONLY the criterion strength; watch the regime flip.
    print("\nP4 same place, two regimes — sweep criterion strength (lr), k fixed:")
    print("   lr      error-to-truth")
    saved = LR
    for lr in (0.0, 0.005, 0.01, 0.02, 0.04, 0.08, 0.12):
        LR = lr
        _, e, _ = run(t, masks, starts, criterion=(lr > 0), consensus="mean")
        if lr == 0.0:
            _, e, _ = run(t, masks, starts, criterion=False, consensus="mean")
        print(f"  {lr:5.3f}   {e:8.4f}")
    LR = saved

    # P5 — ownerless: many independent seed sets; do they reach the SAME fixed point?
    print("\nP5 ownerless / path-independent — COMMONS fixed point across 24 random seed sets:")
    finals = []
    for s in range(24):
        st = make_starts(random.Random(1000 + s))
        bar, _, _ = run(t, masks, st, criterion=True, consensus="mean")
        finals.append(bar)
    center = _mean(finals)
    var = statistics.mean(_dist(f, center) for f in finals)
    print(f"  mean distance of per-seed fixed points from their common center: {var:.6f}")
    print(f"  -> {'YES, ownerless (one attractor)' if var < 1e-3 else 'NO, multiple basins'}")


if __name__ == "__main__":
    main()
