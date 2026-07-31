"""audit_mutations.py -- named fault classes for the checker fault-injection audit.

Each mutator takes a KNOWN-GOOD certificate dict for its family and returns a
mutated dict engineered to fail exactly one named thing. Mutators never import
an Oracle class and never call check()/verify(): building a "known-bad"
fixture by asking the checker under audit whether it looks bad would make the
audit trust the very thing it exists to measure. They only touch plain dicts.

Known-good generators live here too, seeded with a string (random.Random's
str-seed path is a deterministic hash independent of PYTHONHASHSEED, unlike
the plain hash() builtin) so a run is reproducible across processes. The
harness in audit_checkers.py owns comparing checker verdicts against the
labels this module hands it; it does not manufacture the labels itself.
"""
from __future__ import annotations

import random
from itertools import combinations

from harness.certificates.crossing_generator import convex_drawing

# --- Zarankiewicz: known-good certificates -------------------------------------


def zk_known_good_certs(count: int, seed: int) -> list:
    """`count` deterministic K_{2,2}-free witnesses.

    Each column is wired to exactly one row, chosen at random. Two columns can
    then share at most one row, which makes a four-cycle structurally
    impossible for any (m, n) -- no case analysis needed to know it is free.
    """
    rng = random.Random(f"zarankiewicz-good:{seed}")
    out = []
    for _ in range(count):
        m = rng.randint(3, 12)
        n = rng.randint(3, 12)
        edges = [[rng.randrange(m), c] for c in range(n)]
        out.append({"m": m, "n": n, "s": 2, "t": 2,
                    "edges": edges, "edge_count": len(edges)})
    return out


def zk_off_by_one_edge_count(cert: dict) -> dict:
    """Declares one more edge than the certificate exhibits."""
    c = dict(cert)
    c["edge_count"] = cert["edge_count"] + 1
    return c


def zk_duplicated_edge(cert: dict) -> dict:
    """Repeats an existing edge. The declared count matches the now-padded
    list, so only the duplicate-detection path (not the count check) can
    catch this."""
    edges = [list(e) for e in cert["edges"]] + [list(cert["edges"][0])]
    c = dict(cert)
    c["edges"] = edges
    c["edge_count"] = len(edges)
    return c


def zk_added_k22(cert: dict) -> dict:
    """Plants the forbidden structure itself: rows 0 and 1 both wired to
    columns 0 and 1 is a K_{2,2}, regardless of anything else in the graph."""
    if cert["m"] < 2 or cert["n"] < 2:
        raise ValueError("need at least a 2x2 grid to plant a K_2,2")
    edges = {tuple(e) for e in cert["edges"]} | {(0, 0), (0, 1), (1, 0), (1, 1)}
    ordered = sorted(edges)
    c = dict(cert)
    c["edges"] = [list(e) for e in ordered]
    c["edge_count"] = len(ordered)
    return c


def zk_malformed_body(cert: dict) -> dict:
    """Drops a required field outright."""
    c = dict(cert)
    del c["edges"]
    return c


ZARANKIEWICZ_FAULTS = [
    ("off_by_one_edge_count", zk_off_by_one_edge_count),
    ("duplicated_edge", zk_duplicated_edge),
    ("added_k22", zk_added_k22),
    ("malformed_body", zk_malformed_body),
]


# --- rectilinear crossing: known-good certificates ------------------------------


def _diagonal_crossings(n: int, edge_set: set) -> int:
    """Crossing count of a straight-line drawing on points in convex-hull
    order 0..n-1 (the parabola (i, i^2) is exactly that order).

    Independent of the checkers under audit: for four convex-position points
    in hull order i<j<k<l, the pairing (i,k)-(j,l) is the one diagonal pairing
    that crosses, so summing over quadruples where both diagonals are edges
    counts every crossing exactly once. Same argument crossing.py's own
    docstring makes for the complete-graph case, generalized to any subgraph.
    """
    return sum(1 for i, j, k, l in combinations(range(n), 4)
               if (i, k) in edge_set and (j, l) in edge_set)


def cr_known_good_certs(count: int, seed: int) -> list:
    """`count` deterministic drawings with an exactly-known crossing count,
    biased dense so nearly every draw has at least one crossing (needed so
    the undercount mutator has something to subtract from)."""
    rng = random.Random(f"crossing-good:{seed}")
    out = []
    tries = 0
    while len(out) < count and tries < count * 20:
        tries += 1
        n = rng.randint(4, 12)
        pairs = [(a, b) for a in range(n) for b in range(a + 1, n)]
        k = rng.randint(len(pairs) * 2 // 3, len(pairs))
        edges = sorted(rng.sample(pairs, k))
        edge_set = set(edges)
        crossings = _diagonal_crossings(n, edge_set)
        if crossings < 1:
            continue
        out.append({"n": n, "edges": [list(e) for e in edges],
                    "coords": [list(p) for p in convex_drawing(n)],
                    "crossings": crossings})
    if len(out) < count:
        raise ValueError("could not sample enough non-trivial drawings")
    return out


def cr_undercounted_crossings(cert: dict) -> dict:
    """Claims one fewer crossing than the drawing actually has."""
    c = dict(cert)
    c["crossings"] = cert["crossings"] - 1
    return c


def cr_duplicated_point(cert: dict) -> dict:
    """Collapses vertex 1 onto vertex 0."""
    coords = [list(p) for p in cert["coords"]]
    coords[1] = list(coords[0])
    c = dict(cert)
    c["coords"] = coords
    return c


def cr_collinear_points(cert: dict) -> dict:
    """Forces vertices 0, 1, 2 onto the line y = x."""
    coords = [list(p) for p in cert["coords"]]
    coords[0], coords[1], coords[2] = [0, 0], [1, 1], [2, 2]
    c = dict(cert)
    c["coords"] = coords
    return c


def cr_malformed_body(cert: dict) -> dict:
    """Drops a required field outright."""
    c = dict(cert)
    del c["coords"]
    return c


CROSSING_FAULTS = [
    ("undercounted_crossing_total", cr_undercounted_crossings),
    ("duplicated_point", cr_duplicated_point),
    ("collinear_points", cr_collinear_points),
    ("malformed_body", cr_malformed_body),
]
