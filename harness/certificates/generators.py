"""generators.py -- parameterized instances with a difficulty knob.

A criterion pins a generator id and a seed range rather than a static shard, so a
stranger regenerates the exact instance set from a seed instead of downloading a
file and trusting it.

The instance space deliberately EXCLUDES the small square parameters that
published z(m,n;2,2) tables cover. Generating there would make the memorization
control arm meaningless: a model that had read the table would score well without
having searched for anything, and we would have no way to tell the difference.
Excluding them is cheap now and unfixable later, once a run has happened.

Determinism is by an explicit linear congruential step rather than the `random`
module, so an instance depends only on its seed and never on interpreter version,
hash seeding, or call order. A stranger on a different Python must get the same
graph or the whole regeneration promise is theatre.
"""
from __future__ import annotations

from .zarankiewicz import GeneratorError

# Published z(m,n;2,2) tables cover small square cases; those are the ones a
# model could have memorized rather than searched.
EXCLUDED_PAIRS = frozenset(
    (k, k) for k in range(1, 22)
) | frozenset({(2, 3), (3, 2), (3, 4), (4, 3), (4, 5), (5, 4), (5, 6), (6, 5)})

# difficulty -> (m_low, m_high, n_low, n_high), all inclusive.
DIFFICULTY_BANDS = {
    1: (6, 9, 10, 13),
    2: (10, 13, 14, 17),
    3: (14, 18, 19, 23),
    4: (19, 24, 25, 30),
    5: (25, 32, 33, 40),
}

_MASK = (1 << 32) - 1


def _lcg(state: int) -> int:
    """Numerical Recipes LCG. Explicit so the sequence is pinned by this source
    and not by a library version."""
    return (1664525 * state + 1013904223) & _MASK


def instance_space() -> dict:
    """The declared space, so a reader can audit what was and was not generated."""
    return {
        "generator_id": "zarankiewicz.bipartite.v1",
        "generator_version": 1,
        "difficulty_bands": {str(k): list(v) for k, v in DIFFICULTY_BANDS.items()},
        "excluded_pairs": sorted(EXCLUDED_PAIRS),
        "reason": ("excluded pairs are covered by published z(m,n;2,2) tables; "
                   "generating there would make the memorization control arm "
                   "meaningless because a model that read the table scores well "
                   "without having searched"),
    }


def zarankiewicz_instance(*, seed: int, difficulty: int) -> dict:
    """One instance: dimensions plus a small seed witness the solver may extend.

    The seed witness is a partial K_{2,2}-free graph, not an answer. It exists so
    a candidate has a legal starting point and so the checker sees a well formed
    certificate even from a policy that has learned nothing yet.
    """
    if difficulty not in DIFFICULTY_BANDS:
        raise GeneratorError(
            f"difficulty must be one of {sorted(DIFFICULTY_BANDS)}, "
            f"got {difficulty}. Not clamped: a silently adjusted difficulty "
            "would make two runs incomparable.")
    if seed < 0:
        raise GeneratorError("seed must be non-negative")

    m_lo, m_hi, n_lo, n_hi = DIFFICULTY_BANDS[difficulty]
    s = _lcg(seed * 2654435761 + difficulty * 40503 + 1)
    for _ in range(8):                      # discard the low-quality prefix
        s = _lcg(s)

    m = m_lo + (s % (m_hi - m_lo + 1))
    s = _lcg(s)
    n = n_lo + (s % (n_hi - n_lo + 1))

    # Walk out of the excluded region rather than rejecting, so every seed in the
    # criterion's declared range yields an instance.
    guard = 0
    while (m, n) in EXCLUDED_PAIRS and guard < 64:
        n = n_lo + ((n - n_lo + 1) % (n_hi - n_lo + 1))
        guard += 1
    if (m, n) in EXCLUDED_PAIRS:
        raise GeneratorError(
            f"could not leave the excluded region from seed {seed}")

    # A star: one row joined to every column. K_{2,2}-free for any size, because
    # a single row cannot share a second row with anything.
    seed_edges = [(0, j) for j in range(n)]

    return {"generator_id": "zarankiewicz.bipartite.v1",
            "generator_version": 1,
            "seed": seed, "difficulty": difficulty,
            "m": m, "n": n, "s": 2, "t": 2,
            "seed_edges": seed_edges}
