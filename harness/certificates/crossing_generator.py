"""crossing_generator.py -- graphs to draw, with a difficulty knob.

The instance is a GRAPH. The candidate's job is to find integer coordinates for
its vertices that produce few crossing pairs. Nothing here decides how good a
drawing is; that is the checker's job, and how good a drawing COULD be is not
decided anywhere, because this family verifies a count and never claims
optimality.

Two properties every generated instance holds, and both are chosen rather than
incidental:

  1. **Non-planar by edge count.** Every instance carries m > 3n - 6, which by
     Euler's formula means the graph cannot be drawn without crossings at all.
     So the optimum is strictly positive, a candidate cannot win by finding a
     planar embedding, and cr >= m - 3n + 6 gives a lower bound that needs no
     table: any certificate accepted below it would prove the CHECKER wrong.

  2. **Complete graphs are excluded.** The rectilinear crossing numbers of K_n
     are published for small n, so generating one would let a model that had read
     the table score without searching, and we would have no way to tell the
     difference. Excluding them is cheap now and unfixable after a run.

Determinism is an explicit linear congruential step rather than the `random`
module, so an instance depends only on its seed and never on interpreter version
or call order. A stranger on a different Python must get the same graph.
"""
from __future__ import annotations

from .zarankiewicz import GeneratorError

GENERATOR_ID = "crossing.random_nonplanar.v1"
GENERATOR_VERSION = 1

# difficulty -> (n_low, n_high, excess), where excess is how far above the
# planarity threshold 3n-6 the edge count is pushed.
DIFFICULTY_BANDS = {
    1: (7, 9, 2),
    2: (10, 13, 3),
    3: (14, 18, 5),
    4: (19, 26, 8),
    5: (27, 36, 12),
}

_MASK = (1 << 32) - 1


def _lcg(state: int) -> int:
    return (1664525 * state + 1013904223) & _MASK


def instance_space() -> dict:
    """What a criterion pins when it names this generator."""
    return {
        "generator_id": GENERATOR_ID,
        "generator_version": GENERATOR_VERSION,
        "difficulties": sorted(DIFFICULTY_BANDS),
        "bands": {k: {"n_low": v[0], "n_high": v[1], "excess_over_3n_minus_6": v[2]}
                  for k, v in DIFFICULTY_BANDS.items()},
        "guarantees": [
            "m > 3n - 6, so every instance is non-planar and the optimum is "
            "strictly positive",
            "complete graphs are never emitted, because their rectilinear "
            "crossing numbers are published",
        ],
    }


def crossing_instance(*, seed: int, difficulty: int) -> dict:
    """One graph to draw. Deterministic in (seed, difficulty)."""
    if difficulty not in DIFFICULTY_BANDS:
        raise GeneratorError(
            f"difficulty must be one of {sorted(DIFFICULTY_BANDS)}, got "
            f"{difficulty}. Not clamped: a silently adjusted difficulty would "
            "make two runs incomparable.")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise GeneratorError(f"seed must be a non-negative integer, got {seed!r}")

    n_low, n_high, excess = DIFFICULTY_BANDS[difficulty]
    s = _lcg(seed * 2654435761 + difficulty)
    n = n_low + (s % (n_high - n_low + 1))

    complete = n * (n - 1) // 2
    target = 3 * n - 6 + excess
    if target >= complete:
        # Emitting K_n would hand over a published answer. Back off instead of
        # silently shrinking the excess, which would break comparability.
        raise GeneratorError(
            f"difficulty {difficulty} at n={n} would need {target} edges of "
            f"{complete} possible, which is the complete graph or beyond. "
            "Complete graphs are excluded because their rectilinear crossing "
            "numbers are published.")

    all_pairs = [(u, v) for u in range(n) for v in range(u + 1, n)]
    chosen: set = set()
    # A spanning path first, so the graph is connected and the instance is not
    # secretly a smaller problem plus isolated vertices.
    for u in range(n - 1):
        chosen.add((u, u + 1))
    while len(chosen) < target:
        s = _lcg(s)
        chosen.add(all_pairs[s % len(all_pairs)])

    edges = sorted(chosen)
    return {
        "generator_id": GENERATOR_ID,
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "difficulty": difficulty,
        "n": n,
        "edges": [list(e) for e in edges],
        "euler_lower_bound": len(edges) - 3 * n + 6,
    }


def convex_drawing(n: int) -> list:
    """Vertices on the parabola (i, i^2): convex position, no three collinear.

    Used for calibration rather than as a good drawing. A convex point set is the
    WORST case for crossings, since every 4-subset of a convex set contributes a
    crossing whenever both of its diagonals are edges, which for a complete graph
    means exactly C(n,4) crossings. That is an exact answer derivable at any size
    with no published table anywhere in the chain.
    """
    if n < 4:
        raise GeneratorError("a crossing instance needs at least 4 vertices")
    return [[i, i * i] for i in range(n)]
