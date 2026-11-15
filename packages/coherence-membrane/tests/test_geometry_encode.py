from __future__ import annotations

from coherence_membrane.geometry import Geometry, Point, Polyline
from coherence_membrane.geometry_encode import to_coords, to_svg


def test_svg_open_path_has_no_close():
    g = Geometry(paths=(Polyline((Point(0, 0), Point(2, 0))),))
    svg = to_svg(g)
    assert svg.startswith("<svg")
    assert 'viewBox="' in svg
    assert '<path d="M0 0 L2 0"/>' in svg
    assert "Z" not in svg


def test_svg_closed_path_and_unknown_comment():
    g = Geometry(
        paths=(Polyline((Point(0, 0), Point(2, 0), Point(1, 2)), closed=True),),
        unknown=(Point(9, 9), Point(8, 8)),
    )
    svg = to_svg(g)
    assert ' Z"/>' in svg                                  # closed path ends in Z
    assert "<!-- 2 UNVERIFIABLE cells omitted -->" in svg


def test_svg_isolated_point_and_empty():
    svg = to_svg(Geometry(points=(Point(1, 1),)))
    assert "<circle" in svg
    empty = to_svg(Geometry())
    assert empty.startswith("<svg") and empty.rstrip().endswith("</svg>")
    assert 'viewBox="0 0 1 1"' in empty           # empty geometry -> unit viewBox


def test_svg_escapes_stroke():
    # a stroke value containing a quote must not break out of the attribute
    svg = to_svg(Geometry(paths=(Polyline((Point(0, 0), Point(1, 0))),)),
                 stroke='red" onload="x')
    assert 'onload="x' not in svg                 # raw quote did not escape the attr
    assert "&quot;" in svg                        # it was XML-escaped


def test_coords_lines_and_tags():
    g = Geometry(
        paths=(
            Polyline((Point(0, 0), Point(1, 0))),
            Polyline((Point(0, 0), Point(2, 0), Point(1, 2)), closed=True),
        ),
        points=(Point(5, 6),),
        unknown=(Point(9, 9),),
    )
    out = to_coords(g).splitlines()
    assert out[0] == "L 0,0 1,0"
    assert out[1] == "P 0,0 2,0 1,2"
    assert out[2] == "pt 5,6"
    assert out[3] == "unknown 1"


def test_coords_empty():
    assert to_coords(Geometry()) == "empty"


def test_coords_unknown_only_is_not_empty():
    # geometry with only UNVERIFIABLE markers is not "empty" -- it reports them
    assert to_coords(Geometry(unknown=(Point(9, 9),))) == "unknown 1"
