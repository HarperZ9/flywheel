"""Field -> Field operators with honest UNVERIFIABLE propagation."""
from __future__ import annotations

import math

from .field import Field, FieldKind


def threshold(field: Field, t: float) -> Field:
    """Binarise to OCCUPANCY: 1.0 where value >= t, else 0.0. Unknown preserved."""
    values = tuple(1.0 if v >= t else 0.0 for v in field.values)
    return Field(field.width, field.height, FieldKind.OCCUPANCY, values, field.unknown)


def negate(field: Field) -> Field:
    """Polarity inversion. LUMINANCE/OCCUPANCY -> 1 - v; SIGNED_DISTANCE -> -v.
    Kind and unknown mask are preserved."""
    if field.kind is FieldKind.SIGNED_DISTANCE:
        values = tuple(-v for v in field.values)
    else:
        values = tuple(1.0 - v for v in field.values)
    return Field(field.width, field.height, field.kind, values, field.unknown)


def boundary(field: Field, edge_threshold: float = 0.1) -> Field:
    """Edge map (OCCUPANCY): 1.0 where the central-difference gradient magnitude
    >= edge_threshold. Border cells, and any cell whose value or 4-neighbourhood
    is UNVERIFIABLE, are themselves UNVERIFIABLE (honest propagation)."""
    w, h = field.width, field.height
    values = [0.0] * (w * h)
    unknown = [False] * (w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if x == 0 or y == 0 or x == w - 1 or y == h - 1:
                unknown[i] = True
                continue
            neigh = (
                field.index(x - 1, y), field.index(x + 1, y),
                field.index(x, y - 1), field.index(x, y + 1),
            )
            if field.unknown[i] or any(field.unknown[j] for j in neigh):
                unknown[i] = True
                continue
            gx = field.values[field.index(x + 1, y)] - field.values[field.index(x - 1, y)]
            gy = field.values[field.index(x, y + 1)] - field.values[field.index(x, y - 1)]
            values[i] = 1.0 if math.hypot(gx, gy) >= edge_threshold else 0.0
    return Field(w, h, FieldKind.OCCUPANCY, tuple(values), tuple(unknown))


def downscale(field: Field, new_width: int, new_height: int) -> Field:
    """Box-average to a smaller (or equal) grid. A target cell is UNVERIFIABLE if
    ANY source cell in its footprint is UNVERIFIABLE (conservative)."""
    if new_width <= 0 or new_height <= 0:
        raise ValueError("target dimensions must be positive")
    if new_width > field.width or new_height > field.height:
        raise ValueError("downscale cannot upscale")
    w, h = field.width, field.height
    values = [0.0] * (new_width * new_height)
    unknown = [False] * (new_width * new_height)
    for ty in range(new_height):
        y0, y1 = ty * h // new_height, (ty + 1) * h // new_height
        if y1 <= y0:
            y1 = y0 + 1
        for tx in range(new_width):
            x0, x1 = tx * w // new_width, (tx + 1) * w // new_width
            if x1 <= x0:
                x1 = x0 + 1
            total, count, unk = 0.0, 0, False
            for sy in range(y0, y1):
                for sx in range(x0, x1):
                    j = sy * w + sx
                    unk = unk or field.unknown[j]
                    total += field.values[j]
                    count += 1
            ti = ty * new_width + tx
            values[ti] = total / count if count else 0.0
            unknown[ti] = unk
    return Field(new_width, new_height, field.kind, tuple(values), tuple(unknown))


def distance(field: Field) -> Field:
    """OCCUPANCY -> signed distance field (exact Euclidean, brute force).
    Inside (value >= 0.5) is NEGATIVE distance to the nearest outside cell;
    outside is POSITIVE distance to the nearest inside cell; the zero level lies
    between. A cell is UNVERIFIABLE if it is unknown, or if there is no
    opposite-occupancy known cell (no surface to measure from)."""
    if field.kind is not FieldKind.OCCUPANCY:
        raise ValueError("distance requires an OCCUPANCY field")
    w, h = field.width, field.height
    inside: list[tuple[int, int]] = []
    outside: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if field.unknown[i]:
                continue
            (inside if field.values[i] >= 0.5 else outside).append((x, y))
    values = [0.0] * (w * h)
    unknown = [False] * (w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if field.unknown[i]:
                unknown[i] = True
                continue
            is_inside = field.values[i] >= 0.5
            targets = outside if is_inside else inside
            if not targets:
                unknown[i] = True
                continue
            d = min(math.hypot(x - tx, y - ty) for tx, ty in targets)
            values[i] = -d if is_inside else d
    return Field(w, h, FieldKind.SIGNED_DISTANCE, tuple(values), tuple(unknown))


def _sdf_le(sdf: Field, level: float) -> Field:
    """OCCUPANCY 1.0 where the SDF value <= level (unknown propagated)."""
    values = tuple(1.0 if v <= level else 0.0 for v in sdf.values)
    return Field(sdf.width, sdf.height, FieldKind.OCCUPANCY, values, sdf.unknown)


def erode(field: Field, radius: float) -> Field:
    """Shrink the inside by `radius`: keep cells at least `radius` deep inside."""
    return _sdf_le(distance(field), -radius)


def dilate(field: Field, radius: float) -> Field:
    """Grow the inside by `radius`: include cells within `radius` of the inside."""
    return _sdf_le(distance(field), radius)


def open_(field: Field, radius: float) -> Field:
    """Morphological opening: erode then dilate (removes thin features/specks)."""
    return dilate(erode(field, radius), radius)


def close_(field: Field, radius: float) -> Field:
    """Morphological closing: dilate then erode (fills thin gaps/holes)."""
    return erode(dilate(field, radius), radius)


def _csg(a: Field, b: Field, op) -> Field:
    """Per-cell binary op on two same-dim SIGNED_DISTANCE fields. UNVERIFIABLE
    where either input cell is unknown."""
    if a.kind is not FieldKind.SIGNED_DISTANCE or b.kind is not FieldKind.SIGNED_DISTANCE:
        raise ValueError("CSG requires two SIGNED_DISTANCE fields")
    if a.width != b.width or a.height != b.height:
        raise ValueError("CSG requires matching dimensions")
    values = tuple(op(av, bv) for av, bv in zip(a.values, b.values))
    unknown = tuple(au or bu for au, bu in zip(a.unknown, b.unknown))
    return Field(a.width, a.height, FieldKind.SIGNED_DISTANCE, values, unknown)


def union(a: Field, b: Field) -> Field:
    """CSG union of two SDFs: per-cell minimum (inside-or-inside)."""
    return _csg(a, b, min)


def intersect(a: Field, b: Field) -> Field:
    """CSG intersection of two SDFs: per-cell maximum (inside-and-inside)."""
    return _csg(a, b, max)


def diff(a: Field, b: Field) -> Field:
    """CSG difference a \\ b: per-cell max(a, -b)."""
    return _csg(a, b, lambda av, bv: max(av, -bv))


def smin(a: Field, b: Field, k: float = 1.0) -> Field:
    """Smooth CSG union (Inigo Quilez polynomial smin) over two SDFs, blend
    radius `k`. Reduces to min as k -> 0."""
    if k <= 0:
        raise ValueError("smin blend radius k must be positive")

    def _op(av: float, bv: float) -> float:
        h = min(1.0, max(0.0, 0.5 + 0.5 * (bv - av) / k))
        return bv * (1.0 - h) + av * h - k * h * (1.0 - h)

    return _csg(a, b, _op)
