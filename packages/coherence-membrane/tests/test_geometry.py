from __future__ import annotations

import pytest

from coherence_membrane.geometry import Geometry, Point, Polyline


def test_point_is_frozen_and_hashable():
    p = Point(1.0, 2.0)
    assert (p.x, p.y) == (1.0, 2.0)
    assert p == Point(1.0, 2.0)
    assert len({Point(1.0, 2.0), Point(1.0, 2.0)}) == 1   # hashable, value-equal
    with pytest.raises(AttributeError):
        p.x = 5.0                                          # frozen (FrozenInstanceError)


def test_polyline_validation():
    line = Polyline((Point(0, 0), Point(1, 0)))
    assert len(line) == 2 and line.closed is False
    poly = Polyline((Point(0, 0), Point(1, 0), Point(1, 1)), closed=True)
    assert poly.closed is True
    with pytest.raises(ValueError):
        Polyline((Point(0, 0),))                           # < 2 points
    with pytest.raises(ValueError):
        Polyline((Point(0, 0), Point(1, 0)), closed=True)  # closed needs >= 3


def test_geometry_empty_and_bbox():
    assert Geometry().is_empty() is True
    g = Geometry(
        paths=(Polyline((Point(0, 0), Point(2, 0))),),
        points=(Point(-1, 3),),
        unknown=(Point(99, 99),),                          # excluded from bbox
    )
    assert g.is_empty() is False
    assert g.bbox() == (-1.0, 0.0, 2.0, 3.0)
    assert Geometry().bbox() is None


def test_geometry_unknown_only_is_not_empty():
    # UNVERIFIABLE markers are first-class content -> not empty (matches to_coords)
    g = Geometry(unknown=(Point(9, 9),))
    assert g.is_empty() is False
    assert g.bbox() is None        # unknowns still excluded from the drawable bbox
