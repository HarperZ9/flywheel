"""crossing.py -- rectilinear crossings, counted exactly over the integers.

The second construction-certificate family. A candidate is handed a GRAPH and
must return a straight-line drawing of it: integer coordinates for every vertex,
plus the number of crossing pairs that drawing produces. The checker recomputes
that number exactly.

WHAT THIS VERIFIES AND WHAT IT DOES NOT. It verifies the crossing count OF THE
SUBMITTED DRAWING. It does not verify that the drawing is optimal, and the
rectilinear crossing number of the graph is not claimed anywhere. That mirrors
Zarankiewicz, where the checker disposes K_{2,2}-freeness and the edge count and
says nothing about extremality. The count is the objective, lower is better, and
`does_not_prove` says the rest.

Three decisions that carry the family:

  1. **Integer coordinates, so the arithmetic is exact.** Every predicate here is
     the sign of an integer determinant. Python integers are arbitrary precision,
     so there is no overflow and no tolerance anywhere. A drawing with rational
     or floating coordinates would put the accept path at the mercy of rounding,
     which is the gate this family was selected for passing.

  2. **Crossing PAIRS, never crossing points.** Three edges can meet at one
     interior point even when no three VERTICES are collinear. That is three
     crossing pairs and one crossing point, and a candidate minimising points
     could concentrate crossings to shrink its score without improving the
     drawing. Pairs are what the objective counts.

  3. **General position is the candidate's responsibility.** Three collinear
     vertices make "crossing" ambiguous: a T-junction and an overlap are neither
     clearly a crossing nor clearly not one. The candidate chooses the
     coordinates, so a degenerate drawing is an invalid certificate and earns
     FAIL. It is not out of scope. Out of scope is for instances we were handed
     and cannot dispose, not for drawings the candidate chose to make degenerate.

The ground truth here needs no published table, which is why this family was
ranked first. K_n drawn on the parabola (i, i^2) is in convex position with no
three points collinear, and every 4-subset of a convex point set contributes
exactly one crossing, so the count is exactly C(n,4). That is a derivable exact
answer at any size. Separately the Euler bound cr >= m - 3n + 6 makes any accept
below it a detectable false accept on non-planar instances.
"""
from __future__ import annotations

from itertools import combinations

from .base import Coverage, CertificateOracle, OutOfScope, canonical


class CrossingError(ValueError):
    """A malformed drawing certificate."""


def orient(a, b, c) -> int:
    """Sign of the signed area of triangle abc, by the 2x2 cross product.

    Positive is counter-clockwise, negative is clockwise, zero is collinear.
    `crossing_independent.py` computes the same quantity by a 3x3 cofactor
    expansion instead. The two are algebraically identical on purpose: the
    differential test between them cannot catch a mathematical error, only an
    implementation error, and an implementation error in a shared primitive
    would be a common-mode failure on the accept path of both checkers.
    """
    return _sign((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _sign(v: int) -> int:
    return (v > 0) - (v < 0)


def _strict_int(v) -> bool:
    """An honest integer. bool subclasses int in Python, so isinstance(True, int)
    is True, and a coordinate of True would silently read as 1."""
    return isinstance(v, int) and not isinstance(v, bool)


def segments_cross(p, q, r, s) -> bool:
    """Do open segments pq and rs cross at a point interior to both?

    The straddle test: r and s lie on opposite sides of line pq, and p and q lie
    on opposite sides of line rs. Callers must have established general position,
    so no orientation here is zero and touching cases cannot arise.
    """
    return (orient(p, q, r) * orient(p, q, s) < 0
            and orient(r, s, p) * orient(r, s, q) < 0)


def normalize_edges(edges) -> list:
    """Undirected edges as sorted (u, v) with u < v, deduplicated, sorted.

    The canonical form is what the instance binding compares, so [1,0] and [0,1]
    must not read as two different graphs.
    """
    out = set()
    for e in edges:
        if not (isinstance(e, (list, tuple)) and len(e) == 2):
            raise CrossingError(f"edge {e!r} is not a pair")
        u, v = e
        if not (_strict_int(u) and _strict_int(v)):
            raise CrossingError(f"edge {e!r} has non-integer endpoints")
        if u == v:
            raise CrossingError(f"self loop at {u}")
        out.add((u, v) if u < v else (v, u))
    return sorted(out)


def count_crossings(coords: list, edges: list) -> int:
    """Crossing pairs of a straight-line drawing. O(m^2) straddle tests.

    Edges sharing an endpoint are skipped: they meet AT the shared vertex, which
    is not interior to either segment, so they do not cross.
    """
    total = 0
    for (a, b), (c, d) in combinations(edges, 2):
        if len({a, b, c, d}) < 4:
            continue
        if segments_cross(coords[a], coords[b], coords[c], coords[d]):
            total += 1
    return total


def general_position(coords: list) -> tuple:
    """(ok, reason). No three vertices collinear, and no two coincident."""
    n = len(coords)
    for i, j in combinations(range(n), 2):
        if coords[i] == coords[j]:
            return False, f"vertices {i} and {j} share the point {coords[i]}"
    for i, j, k in combinations(range(n), 3):
        if orient(coords[i], coords[j], coords[k]) == 0:
            return False, f"vertices {i}, {j}, {k} are collinear"
    return True, ""


def well_formed(cert: dict) -> tuple:
    """(ok, reason). Structure only, before any geometry."""
    for key in ("n", "edges", "coords", "crossings"):
        if key not in cert:
            return False, f"missing {key!r}"
    n = cert["n"]
    if not _strict_int(n) or n < 4:
        return False, f"n={n!r} must be an integer of at least 4"
    if not _strict_int(cert["crossings"]) or cert["crossings"] < 0:
        return False, f"crossings={cert['crossings']!r} must be a non-negative integer"
    coords = cert["coords"]
    if not isinstance(coords, list) or len(coords) != n:
        return False, f"coords must be a list of exactly n={n} points"
    for i, p in enumerate(coords):
        if not (isinstance(p, list) and len(p) == 2
                and all(_strict_int(v) for v in p)):
            return False, f"coords[{i}]={p!r} is not a pair of integers"
    try:
        edges = normalize_edges(cert["edges"])
    except CrossingError as e:
        return False, str(e)
    for u, v in edges:
        if not (0 <= u < n and 0 <= v < n):
            return False, f"edge ({u},{v}) references a vertex outside 0..{n-1}"
    return True, ""


class CrossingOracle(CertificateOracle):
    """Exact rectilinear crossing counter. Data only; executes nothing."""

    oracle_type = "crossing_certificate"
    family = "rectilinear_crossing"
    # n is capped well below what checker A could handle, because the held-out
    # checker is O(n^4) and has to stay runnable as an audit.
    scope_bounds = {"n_max": 64, "edges_max": 2016, "max_abs_coord_max": 1 << 20}

    # The instance IS the graph. The candidate supplies only the drawing, so a
    # certificate that redraws a different graph has not answered the question.
    binding_keys = ("n", "edges_key")

    family_not_proven = (
        "NOT_PROVES_OPTIMALITY: this verifies the SUBMITTED object. The optimal "
        "value for the instance is not computed, not bounded, and not claimed "
        "anywhere.",
    )

    def declared_parameters(self, cert: dict) -> dict:
        edges = normalize_edges(cert["edges"])
        coords = cert.get("coords") or []
        return {"n": int(cert["n"]),
                "edges": len(edges),
                "edges_key": canonical(edges),
                "max_abs_coord": max((abs(v) for p in coords
                                      for v in p if _strict_int(v)), default=0)}

    def instance_binding(self, task) -> dict | None:
        """Canonicalize the instance's edge list the same way the certificate's
        is canonicalized, so the two are compared as graphs and not as text."""
        if not isinstance(task, dict) or "n" not in task or "edges" not in task:
            return None
        try:
            return {"n": int(task["n"]),
                    "edges_key": canonical(normalize_edges(task["edges"]))}
        except (CrossingError, TypeError, ValueError):
            return None

    def objective_of(self, cert: dict) -> str:
        # Lower is better here, unlike Zarankiewicz where higher is better. The
        # direction lives in the family rather than in the hashed criterion,
        # because adding a field to Criterion would rehash every existing one.
        return str(cert.get("crossings", ""))

    def check(self, cert: dict) -> tuple[bool, str, Coverage]:
        exact = Coverage(predicate_exact=True, search_space_enumerated=True,
                         enumerated_fraction="1", stop_reason="complete",
                         guarantee_weakens_above=None)

        ok, why = well_formed(cert)
        if not ok:
            return False, f"malformed drawing: {why}", exact

        coords = [tuple(p) for p in cert["coords"]]
        edges = normalize_edges(cert["edges"])

        ok, why = general_position(coords)
        if not ok:
            # The candidate chose these coordinates, so this is its error and
            # not a gap in what we implement.
            return False, (f"drawing is degenerate: {why}. A straight-line "
                           "drawing must be in general position for crossings "
                           "to be well defined."), exact

        actual = count_crossings(coords, edges)
        claimed = cert["crossings"]
        if actual != claimed:
            return False, (f"claimed {claimed} crossing pairs, drawing has "
                           f"{actual}"), exact

        # Reported, never enforced. A candidate cannot be below it, so a
        # certificate that is would mean the checker is wrong, not the drawing.
        euler = len(edges) - 3 * cert["n"] + 6
        note = f" (Euler lower bound for a non-planar graph: {max(euler, 0)})"
        return True, (f"{actual} crossing pairs verified over {len(edges)} edges "
                      f"and {cert['n']} vertices{note}"), exact
