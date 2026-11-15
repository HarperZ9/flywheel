from __future__ import annotations

import pytest

from coherence_membrane.field import Field, FieldKind
from coherence_membrane.geometry import Geometry, Point, Polyline
from coherence_membrane.geometry_ops import contour, stitch, simplify, simplify_geometry


def _f(w, h, vals, unknown=None, kind=FieldKind.LUMINANCE):
    if unknown is None:
        unknown = (False,) * (w * h)
    return Field(w, h, kind, tuple(float(v) for v in vals), tuple(unknown))


def test_contour_single_vertical_segment():
    # 2x2: left column above, right column below -> one vertical segment at x=0.5
    f = _f(2, 2, [1.0, 0.0, 1.0, 0.0])   # TL=1 TR=0 / BL=1 BR=0
    g = contour(f, 0.5)
    assert len(g.paths) == 1
    seg = g.paths[0]
    pts = set(seg.points)
    assert pts == {Point(0.5, 0.0), Point(0.5, 1.0)}
    assert g.unknown == ()


def test_contour_level_shifts_crossing():
    # values 0 and 1 across each row; the level shifts the crossing along x.
    f = _f(2, 2, [0.0, 1.0, 0.0, 1.0])   # left column below, right column above
    g = contour(f, 0.25)
    assert len(g.paths) == 1
    assert g.unknown == ()
    assert set(g.paths[0].points) == {Point(0.25, 0.0), Point(0.25, 1.0)}


def test_contour_unknown_corner_is_unverifiable():
    f = _f(2, 2, [1.0, 0.0, 1.0, 0.0],
           unknown=(False, True, False, False))   # TR unknown
    g = contour(f, 0.5)
    assert g.paths == ()
    assert g.unknown == (Point(0.5, 0.5),)


def test_contour_saddle_emits_two_non_crossing_segments():
    f = _f(2, 2, [1.0, 0.0, 0.0, 1.0])   # TL=1 TR=0 / BL=0 BR=1  (alternating)
    g = contour(f, 0.5)
    assert g.unknown == ()
    # TL & BR are above; the two arcs must isolate those corners, NOT use the
    # crossing pairing (vertical (0.5,0)-(0.5,1) + horizontal (0,0.5)-(1,0.5)).
    seg_sets = {frozenset(s.points) for s in g.paths}
    assert seg_sets == {
        frozenset({Point(0.5, 0.0), Point(1.0, 0.5)}),
        frozenset({Point(0.5, 1.0), Point(0.0, 0.5)}),
    }


def test_stitch_joins_open_chain():
    segs = Geometry(paths=(
        Polyline((Point(0, 0), Point(1, 0))),
        Polyline((Point(2, 0), Point(1, 0))),   # reversed; shares (1,0)
        Polyline((Point(2, 0), Point(2, 1))),
    ))
    out = stitch(segs)
    assert len(out.paths) == 1
    chain = out.paths[0]
    assert chain.closed is False
    # the chain is geometrically contiguous (adjacent points share a segment),
    # in one of the two valid orientations
    assert chain.points in {
        (Point(0, 0), Point(1, 0), Point(2, 0), Point(2, 1)),
        (Point(2, 1), Point(2, 0), Point(1, 0), Point(0, 0)),
    }


def test_stitch_detects_closed_loop():
    sq = Geometry(paths=(
        Polyline((Point(0, 0), Point(1, 0))),
        Polyline((Point(1, 0), Point(1, 1))),
        Polyline((Point(1, 1), Point(0, 1))),
        Polyline((Point(0, 1), Point(0, 0))),
    ))
    out = stitch(sq)
    assert len(out.paths) == 1
    assert out.paths[0].closed is True
    assert len(out.paths[0].points) == 4         # 4 distinct corners, seam not repeated


def test_stitch_passes_through_points_and_unknown():
    g = Geometry(
        paths=(Polyline((Point(0, 0), Point(1, 0))),),
        points=(Point(5, 5),),
        unknown=(Point(9, 9),),
    )
    out = stitch(g)
    assert len(out.paths) == 1 and out.paths[0].closed is False
    assert out.points == (Point(5, 5),)
    assert out.unknown == (Point(9, 9),)


def test_simplify_drops_collinear():
    line = Polyline((Point(0, 0), Point(1, 0), Point(2, 0), Point(3, 0)))
    out = simplify(line, 0.01)
    assert out.points == (Point(0, 0), Point(3, 0))


def test_simplify_keeps_significant_vertex():
    spike = Polyline((Point(0, 0), Point(1, 5), Point(2, 0)))
    out = simplify(spike, 0.01)
    assert out.points == (Point(0, 0), Point(1, 5), Point(2, 0))   # spike kept


def test_simplify_validates_and_short_circuits():
    seg = Polyline((Point(0, 0), Point(9, 9)))
    assert simplify(seg, 1.0) is seg                                # < 3 points: unchanged
    with pytest.raises(ValueError):
        simplify(seg, -1.0)


def test_simplify_geometry_passes_through():
    g = Geometry(
        paths=(Polyline((Point(0, 0), Point(1, 0), Point(2, 0)),),),
        points=(Point(7, 7),),
        unknown=(Point(8, 8),),
    )
    out = simplify_geometry(g, 0.01)
    assert out.paths[0].points == (Point(0, 0), Point(2, 0))
    assert out.points == (Point(7, 7),)
    assert out.unknown == (Point(8, 8),)


def test_simplify_closed_keeps_flag_and_drops_collinear():
    # closed quad with a redundant collinear midpoint (1,0) on the bottom edge
    quad = Polyline(
        (Point(0, 0), Point(1, 0), Point(2, 0), Point(2, 2), Point(0, 2)),
        closed=True,
    )
    out = simplify(quad, 0.01)
    assert out.closed is True
    assert Point(1, 0) not in out.points
    assert len(out.points) >= 3


def test_simplify_closed_collapse_guard_returns_original():
    tri = Polyline((Point(0, 0), Point(4, 0), Point(2, 1)), closed=True)
    # a large epsilon would collapse it below 3 points -> original returned
    assert simplify(tri, 100.0) is tri
