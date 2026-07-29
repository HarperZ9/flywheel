"""crossing_independent.py -- the held-out crossing checker, by a different route.

`crossing.py` iterates over PAIRS OF EDGES and applies a straddle test. This
module iterates over QUADRUPLES OF VERTICES and computes a convex hull. Both
decide the same predicate, and they share no step.

The mathematics they rely on differs, which is the point:

  primary   two vertex-disjoint segments cross iff each straddles the line
            through the other. O(m^2) straddle tests.

  held out  two vertex-disjoint edges cross iff their four endpoints are in
            CONVEX POSITION and the two edges are the diagonal pairing of that
            convex quadrilateral. Every crossing pair sits in exactly one
            quadruple, and a convex quadruple has exactly one crossing pairing
            out of the three, so summing over quadruples counts each crossing
            once. O(n^4) hull constructions.

A cross-check between two implementations of the same idea is not a held-out
check, so `orient` is deliberately written twice by different expression trees:
a 2x2 cross product in the primary, and a 3x3 cofactor expansion here. Those are
algebraically identical, and being honest about what that buys matters.
`differential_orient` cannot detect a mathematical error, because there is no
mathematical disagreement to find. It detects a TYPO, and a typo in a shared
primitive would be a common-mode failure on the accept path of both checkers,
which is the one failure a cross-check would otherwise be blind to.

Cost: this checker is asymptotically more expensive than the primary. It is built
to run as a periodic held-out audit rather than on every rollout.
"""
from __future__ import annotations

from itertools import combinations

from .base import Coverage, CertificateOracle
from .crossing import (
    CrossingError, CrossingOracle, general_position, normalize_edges, orient,
    well_formed,
)
from .independent import AgreementError


def orient3(a, b, c) -> int:
    """Sign of the 3x3 determinant

        | a.x  a.y  1 |
        | b.x  b.y  1 |
        | c.x  c.y  1 |

    expanded along the last column. Same value as `crossing.orient`, computed by
    a different expression tree so a slip in one does not appear in both.
    """
    det = (a[0] * (b[1] - c[1])
           - a[1] * (b[0] - c[0])
           + (b[0] * c[1] - b[1] * c[0]))
    return (det > 0) - (det < 0)


def differential_orient(points) -> tuple:
    """(agree, first_disagreement). Compare the two primitives over every triple.

    Honest bound, stated because it is easy to overstate: agreement here does not
    establish that the shared mathematics is right. Both could implement the same
    wrong idea. It establishes only that they were typed correctly relative to
    each other.
    """
    for a, b, c in combinations(points, 3):
        if orient(a, b, c) != orient3(a, b, c):
            return False, (a, b, c)
    return True, None


def convex_hull_4(pts) -> list:
    """Indices of the convex hull of four points, counter-clockwise.

    Andrew's monotone chain, which uses orientation only and never a straddle
    test. Returns four indices when the points are in convex position, and three
    when one point lies inside the triangle of the other three.
    """
    order = sorted(range(len(pts)), key=lambda i: (pts[i][0], pts[i][1]))

    def build(seq):
        stack: list = []
        for i in seq:
            while len(stack) >= 2 and orient3(pts[stack[-2]], pts[stack[-1]],
                                              pts[i]) <= 0:
                stack.pop()
            stack.append(i)
        return stack

    lower = build(order)
    upper = build(reversed(order))
    return lower[:-1] + upper[:-1]


def count_crossings_by_quadruples(coords: list, edges: list) -> int:
    """Crossing pairs, by convex position over vertex quadruples."""
    edge_set = set(edges)
    n = len(coords)
    total = 0
    for quad in combinations(range(n), 4):
        pts = [coords[i] for i in quad]
        hull = convex_hull_4(pts)
        if len(hull) != 4:
            continue                    # one point inside: no pairing crosses
        # In hull order the diagonals join opposite corners.
        d1 = quad[hull[0]], quad[hull[2]]
        d2 = quad[hull[1]], quad[hull[3]]
        d1 = d1 if d1[0] < d1[1] else (d1[1], d1[0])
        d2 = d2 if d2[0] < d2[1] else (d2[1], d2[0])
        if d1 in edge_set and d2 in edge_set:
            total += 1
    return total


class IndependentCrossingOracle(CertificateOracle):
    """The held-out crossing checker. Same contract, different internals."""

    oracle_type = "crossing_certificate_independent"
    family = "rectilinear_crossing"
    scope_bounds = {"n_max": 64, "edges_max": 2016, "max_abs_coord_max": 1 << 20}
    binding_keys = ("n", "edges_key")

    family_not_proven = (
        "NOT_PROVES_OPTIMALITY: this verifies the SUBMITTED object. The optimal "
        "value for the instance is not computed, not bounded, and not claimed "
        "anywhere.",
    )

    # The parameter and binding contracts are part of the CRITERION, not part of
    # the algorithm, so sharing them is correct. Sharing the counting would not
    # be, and it is not shared.
    declared_parameters = CrossingOracle.declared_parameters
    instance_binding = CrossingOracle.instance_binding
    objective_of = CrossingOracle.objective_of

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
            return False, f"drawing is degenerate: {why}", exact

        agree, where = differential_orient(coords)
        if not agree:
            # Never a candidate error. Two implementations of one primitive
            # disagreeing means our code is wrong, so it must not read as FAIL.
            raise AgreementError(
                "the two orientation primitives disagree at "
                f"{where}, which means one of them is mistyped. Refusing to "
                "grade a candidate with a broken checker.")

        actual = count_crossings_by_quadruples(coords, edges)
        claimed = cert["crossings"]
        if actual != claimed:
            return False, (f"claimed {claimed} crossing pairs, convex-position "
                           f"count over quadruples gives {actual}"), exact
        return True, (f"{actual} crossing pairs confirmed by convex position "
                      f"over all {cert['n']} choose 4 vertex quadruples"), exact
