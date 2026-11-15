"""Geometry bridges + operators: contour (Field -> Geometry), stitch, simplify.

contour is the Field->Geometry functor (marching squares). stitch and simplify
are Geometry->Geometry operators. All are pure; UNVERIFIABLE is propagated
honestly (an unknown contour cell becomes an unknown marker, never a guessed
line).
"""
from __future__ import annotations

import math
from collections import defaultdict

from .field import Field
from .geometry import Geometry, Point, Polyline


def _interp(ax, ay, av, bx, by, bv, level):
    """Linear crossing point on edge A->B at `level`. A and B MUST straddle
    `level`. Endpoints are ordered canonically by (y, x) so the SAME physical grid
    edge yields a bit-identical Point from either adjacent cell -> exact-endpoint
    stitching needs no epsilon."""
    if (ay, ax) > (by, bx):
        ax, ay, av, bx, by, bv = bx, by, bv, ax, ay, av
    t = (level - av) / (bv - av)
    return Point(ax + t * (bx - ax), ay + t * (by - ay))


def _edge(ax, ay, av, bx, by, bv, level):
    """Crossing Point on edge A-B if exactly one endpoint is 'above' (>= level),
    else None."""
    if (av >= level) == (bv >= level):
        return None
    return _interp(ax, ay, av, bx, by, bv, level)


def contour(field: Field, level: float = 0.5) -> Geometry:
    """Marching-squares iso-contour of `field` at `level` -> Geometry of 2-point
    segments (unstitched; feed to `stitch` to join). A cell (2x2 corner window)
    with any UNVERIFIABLE corner emits no segment and its centre is recorded in
    Geometry.unknown. A corner is 'above' iff value >= level. Saddle cells (4
    crossings) are disambiguated by the 4-corner average. For SIGNED_DISTANCE
    fields pass level=0.0."""
    w, h = field.width, field.height
    segs: list[Polyline] = []
    unknown: list[Point] = []
    for cy in range(h - 1):
        for cx in range(w - 1):
            corners = ((cx, cy), (cx + 1, cy), (cx + 1, cy + 1), (cx, cy + 1))
            if any(field.is_unknown(x, y) for x, y in corners):
                unknown.append(Point(cx + 0.5, cy + 0.5))
                continue
            tl = field.at(cx, cy)
            tr = field.at(cx + 1, cy)
            br = field.at(cx + 1, cy + 1)
            bl = field.at(cx, cy + 1)
            top = _edge(cx, cy, tl, cx + 1, cy, tr, level)              # TL-TR
            right = _edge(cx + 1, cy, tr, cx + 1, cy + 1, br, level)    # TR-BR
            bottom = _edge(cx, cy + 1, bl, cx + 1, cy + 1, br, level)   # BL-BR
            left = _edge(cx, cy, tl, cx, cy + 1, bl, level)             # TL-BL
            present = [e for e in (top, right, bottom, left) if e is not None]
            if len(present) == 2:
                segs.append(Polyline((present[0], present[1])))
            elif len(present) == 4:
                center = (tl + tr + br + bl) / 4.0
                if (center >= level) == (tl >= level):
                    segs.append(Polyline((top, right)))
                    segs.append(Polyline((bottom, left)))
                else:
                    segs.append(Polyline((top, left)))
                    segs.append(Polyline((right, bottom)))
    return Geometry(paths=tuple(segs), unknown=tuple(unknown))


def _next_seg(ends, used, point):
    for i in ends.get(point, ()):
        if not used[i]:
            return i
    return None


def stitch(geometry: Geometry) -> Geometry:
    """Join open 2-point segments into maximal polylines by exact shared
    endpoints. A chain returning to its start becomes a closed Polyline. Isolated
    points, unknown markers, and non-(open 2-point) paths pass through unchanged.
    Junctions of >2 segments (T-junctions) are resolved greedily (first unused
    neighbour wins): the output is valid but non-canonical for branching inputs."""
    def _is_seg(p: Polyline) -> bool:
        return len(p.points) == 2 and not p.closed

    segs = [(p.points[0], p.points[1]) for p in geometry.paths if _is_seg(p)]
    passthrough = tuple(p for p in geometry.paths if not _is_seg(p))

    ends = defaultdict(list)
    for i, (a, b) in enumerate(segs):
        ends[a].append(i)
        ends[b].append(i)

    used = [False] * len(segs)
    chains: list[Polyline] = []
    for s0 in range(len(segs)):
        if used[s0]:
            continue
        used[s0] = True
        a, b = segs[s0]
        chain = [a, b]
        # grow at the tail
        while True:
            tail = chain[-1]
            nxt = _next_seg(ends, used, tail)
            if nxt is None:
                break
            used[nxt] = True
            x, y = segs[nxt]
            chain.append(y if x == tail else x)
            if chain[-1] == chain[0]:
                break
        # grow at the head (unless already closed)
        if chain[-1] != chain[0]:
            while True:
                head = chain[0]
                nxt = _next_seg(ends, used, head)
                if nxt is None:
                    break
                used[nxt] = True
                x, y = segs[nxt]
                chain.insert(0, y if x == head else x)
                if chain[0] == chain[-1]:
                    break
        closed = len(chain) > 3 and chain[0] == chain[-1]
        if closed:
            chain = chain[:-1]
        chains.append(Polyline(tuple(chain), closed=closed))

    return Geometry(
        paths=passthrough + tuple(chains),
        points=geometry.points,
        unknown=geometry.unknown,
    )


def _perp_dist(p: Point, a: Point, b: Point) -> float:
    """Perpendicular distance from p to the line through a-b (point distance if
    a == b)."""
    dx, dy = b.x - a.x, b.y - a.y
    if dx == 0.0 and dy == 0.0:
        return math.hypot(p.x - a.x, p.y - a.y)
    return abs(dx * (a.y - p.y) - (a.x - p.x) * dy) / math.hypot(dx, dy)


def _dp(points: list[Point], eps: float) -> list[Point]:
    if len(points) < 3:
        return list(points)
    a, b = points[0], points[-1]
    idx, dmax = 1, -1.0   # always reassigned before use (first interior pt wins)
    for i in range(1, len(points) - 1):
        d = _perp_dist(points[i], a, b)
        if d > dmax:
            idx, dmax = i, d
    if dmax > eps:
        left = _dp(points[: idx + 1], eps)
        right = _dp(points[idx:], eps)
        return left[:-1] + right
    return [a, b]


def simplify(polyline: Polyline, epsilon: float) -> Polyline:
    """Douglas-Peucker simplification. A vertex farther than `epsilon` from its
    working chord is kept (boundary: a vertex at exactly `epsilon` is kept).
    Closed polylines keep their first/last anchors and the closed flag; if
    simplifying would drop a closed polyline below 3 points, the original is
    returned unchanged."""
    if epsilon < 0:
        raise ValueError("epsilon must be >= 0")
    if len(polyline.points) < 3:
        return polyline
    kept = _dp(list(polyline.points), epsilon)
    if polyline.closed and len(kept) < 3:
        return polyline
    return Polyline(tuple(kept), closed=polyline.closed)


def simplify_geometry(geometry: Geometry, epsilon: float) -> Geometry:
    """Douglas-Peucker every path; points + unknown pass through."""
    return Geometry(
        paths=tuple(simplify(p, epsilon) for p in geometry.paths),
        points=geometry.points,
        unknown=geometry.unknown,
    )
