from __future__ import annotations

import math

from coherence_membrane.field import Field, FieldKind
from coherence_membrane.field_ops import threshold, negate, boundary, downscale, distance, erode, dilate, open_, close_


def _f(w, h, vals, unknown=None, kind=FieldKind.LUMINANCE):
    if unknown is None:
        unknown = (False,) * (w * h)
    return Field(w, h, kind, tuple(float(v) for v in vals), tuple(unknown))


def test_threshold_to_occupancy():
    occ = threshold(_f(2, 2, [0.2, 0.6, 0.5, 0.9]), 0.5)
    assert occ.kind is FieldKind.OCCUPANCY
    assert occ.values == (0.0, 1.0, 1.0, 1.0)


def test_threshold_preserves_unknown():
    occ = threshold(_f(2, 1, [0.2, 0.9], unknown=(True, False)), 0.5)
    assert occ.unknown == (True, False)


def test_negate_luminance():
    assert negate(_f(2, 1, [0.0, 1.0])).values == (1.0, 0.0)


def test_negate_signed_distance():
    f = _f(2, 1, [-2.0, 3.0], kind=FieldKind.SIGNED_DISTANCE)
    out = negate(f)
    assert out.values == (2.0, -3.0)
    assert out.kind is FieldKind.SIGNED_DISTANCE


def test_boundary_detects_edge_and_marks_border_unknown():
    # 4x4, each row [0,0,0,1] => vertical edge between col2 and col3
    f = _f(4, 4, [0, 0, 0, 1] * 4)
    edges = boundary(f, edge_threshold=0.1)
    assert edges.kind is FieldKind.OCCUPANCY
    assert edges.is_unknown(0, 0) and edges.is_unknown(3, 3)   # border
    assert edges.at(2, 1) == 1.0                                # on the edge
    assert edges.at(1, 1) == 0.0                                # flat region


def test_boundary_propagates_unknown():
    unk = [False] * 9
    unk[4] = True  # center of a 3x3 is unknown
    edges = boundary(_f(3, 3, [0.0] * 9, unknown=unk), 0.1)
    assert edges.is_unknown(1, 1)  # the only interior cell is the unknown one


def test_downscale_box_average_and_unknown():
    small = downscale(_f(2, 2, [0.0, 1.0, 1.0, 0.0]), 1, 1)
    assert small.width == 1 and small.height == 1
    assert abs(small.at(0, 0) - 0.5) < 1e-9
    f2 = _f(2, 2, [0.0, 1.0, 1.0, 0.0], unknown=(False, True, False, False))
    assert downscale(f2, 1, 1).is_unknown(0, 0)


def test_negate_preserves_unknown_mask():
    f = _f(2, 1, [0.2, 0.8], unknown=(True, False))
    out = negate(f)
    assert out.unknown == (True, False)


def test_negate_occupancy_is_one_minus_v():
    f = _f(2, 1, [0.0, 1.0], kind=FieldKind.OCCUPANCY)
    out = negate(f)
    assert out.kind is FieldKind.OCCUPANCY
    assert out.values == (1.0, 0.0)


def test_downscale_raises_on_upscale():
    import pytest
    # 2-wide field, asking for 3 cols -> upscale -> ValueError
    f = _f(2, 2, [0.0, 1.0, 0.5, 0.5])
    with pytest.raises(ValueError):
        downscale(f, 3, 1)


def test_downscale_raises_on_nonpositive_dims():
    import pytest
    f = _f(2, 2, [0.0, 1.0, 0.5, 0.5])
    with pytest.raises(ValueError):
        downscale(f, 0, 1)


def test_distance_single_inside_cell():
    # 5x5, single inside cell at (2,2); rest outside
    vals = [0.0] * 25
    vals[2 * 5 + 2] = 1.0
    f = _f(5, 5, vals, kind=FieldKind.OCCUPANCY)
    sdf = distance(f)
    assert sdf.kind is FieldKind.SIGNED_DISTANCE
    assert sdf.at(2, 2) == -1.0          # inside, nearest outside is 1 away
    assert sdf.at(1, 2) == 1.0           # outside, nearest inside (2,2) is 1 away
    assert sdf.at(0, 2) == 2.0           # 2 away
    assert abs(sdf.at(0, 0) - math.hypot(2, 2)) < 1e-9


def test_distance_no_surface_is_unverifiable():
    f = _f(2, 2, [1.0, 1.0, 1.0, 1.0], kind=FieldKind.OCCUPANCY)  # all inside
    sdf = distance(f)
    assert all(sdf.is_unknown(x, y) for y in range(2) for x in range(2))


def test_distance_propagates_unknown_and_requires_occupancy():
    f = _f(2, 1, [1.0, 0.0], unknown=(True, False), kind=FieldKind.OCCUPANCY)
    assert distance(f).is_unknown(0, 0)
    import pytest
    with pytest.raises(ValueError):
        distance(_f(2, 1, [0.0, 1.0], kind=FieldKind.LUMINANCE))


def _occ5_block():  # 5x5 with a 3x3 inside block at x,y in 1..3
    vals = [0.0] * 25
    for y in range(1, 4):
        for x in range(1, 4):
            vals[y * 5 + x] = 1.0
    return _f(5, 5, vals, kind=FieldKind.OCCUPANCY)


def test_erode_shrinks_to_core():
    eroded = erode(_occ5_block(), 2.0)   # keep only sdf <= -2  => center only
    assert eroded.kind is FieldKind.OCCUPANCY
    assert eroded.at(2, 2) == 1.0
    assert sum(eroded.values) == 1.0     # exactly one inside cell remains


def test_dilate_grows_to_plus():
    vals = [0.0] * 25
    vals[2 * 5 + 2] = 1.0
    grown = dilate(_f(5, 5, vals, kind=FieldKind.OCCUPANCY), 1.0)  # sdf <= 1
    inside = {(x, y) for y in range(5) for x in range(5) if grown.at(x, y) == 1.0}
    assert inside == {(2, 2), (1, 2), (3, 2), (2, 1), (2, 3)}  # plus shape


def test_open_removes_speck():
    # 5x5: a 3x3 block plus an isolated speck at (0,0)
    vals = [0.0] * 25
    for y in range(1, 4):
        for x in range(1, 4):
            vals[y * 5 + x] = 1.0
    vals[0] = 1.0  # speck
    opened = open_(_f(5, 5, vals, kind=FieldKind.OCCUPANCY), 2.0)
    assert opened.at(0, 0) == 0.0        # speck removed by opening
    assert opened.at(2, 2) == 1.0        # core survives


def test_close_fills_hole():
    # 5x5 solid 3x3 block with a 1-cell hole at the center (2,2)
    vals = [0.0] * 25
    for y in range(1, 4):
        for x in range(1, 4):
            vals[y * 5 + x] = 1.0
    vals[2 * 5 + 2] = 0.0  # hole
    closed = close_(_f(5, 5, vals, kind=FieldKind.OCCUPANCY), 1.0)
    assert closed.at(2, 2) == 1.0        # hole filled by closing


def _sdf(w, h, vals, unknown=None):
    if unknown is None:
        unknown = (False,) * (w * h)
    return Field(w, h, FieldKind.SIGNED_DISTANCE, tuple(vals), tuple(unknown))


def test_union_is_min_intersect_is_max():
    from coherence_membrane.field_ops import union, intersect
    a = _sdf(2, 1, [-1.0, 2.0])
    b = _sdf(2, 1, [1.0, -2.0])
    assert union(a, b).values == (-1.0, -2.0)
    assert intersect(a, b).values == (1.0, 2.0)


def test_csg_propagates_unknown_and_checks_dims():
    import pytest
    from coherence_membrane.field_ops import union
    a = _sdf(2, 1, [0.0, 0.0], unknown=(True, False))
    b = _sdf(2, 1, [0.0, 0.0])
    assert union(a, b).is_unknown(0, 0)
    with pytest.raises(ValueError):
        union(a, _sdf(3, 1, [0.0, 0.0, 0.0]))   # dim mismatch


def test_diff_is_a_minus_b():
    from coherence_membrane.field_ops import diff
    a = _sdf(2, 1, [-1.0, 2.0])
    b = _sdf(2, 1, [1.0, -2.0])
    # diff = max(a, -b): max(-1, -1) = -1 ; max(2, 2) = 2
    assert diff(a, b).values == (-1.0, 2.0)


def test_smin_is_smoother_than_min():
    from coherence_membrane.field_ops import smin
    a = _sdf(1, 1, [0.0])
    b = _sdf(1, 1, [0.0])
    s = smin(a, b, 1.0).at(0, 0)
    assert s < 0.0                      # smooth dip below min(0,0)=0
    assert abs(s - (-0.25)) < 1e-9      # IQ poly: h=0.5 -> -k*0.25
    import pytest
    with pytest.raises(ValueError):
        smin(a, b, 0.0)
