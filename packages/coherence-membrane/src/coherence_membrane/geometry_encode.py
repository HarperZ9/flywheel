"""Encoders: Geometry -> text media. Each is pure and token-cheap (plotter-native
vectors a model can read). Witnessing happens in the organ layer (see
organs/contour.py), as with the braille encoder."""
from __future__ import annotations

import html

from .geometry import Geometry, Polyline


def _fmt(v: float, decimals: int) -> str:
    """Round to `decimals`; strip trailing zeros and a lone trailing dot;
    normalise '-0' to '0'."""
    s = f"{v:.{decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def _path_d(poly: Polyline, decimals: int) -> str:
    cmds = [
        f"{'M' if i == 0 else 'L'}{_fmt(p.x, decimals)} {_fmt(p.y, decimals)}"
        for i, p in enumerate(poly.points)
    ]
    if poly.closed:
        cmds.append("Z")
    return " ".join(cmds)


def to_svg(
    geometry: Geometry,
    *,
    decimals: int = 2,
    stroke: str = "black",
    stroke_width: float = 1.0,
    pad: float = 1.0,
) -> str:
    """Geometry -> a standalone <svg> string (paths as <path>, isolated points as
    <circle>). Unknown markers are reported in a trailing comment, never drawn.
    `stroke` is XML-escaped so the output is always well-formed."""
    stroke = html.escape(stroke, quote=True)
    bb = geometry.bbox()
    if bb is None:
        minx, miny, vw, vh = 0.0, 0.0, 1.0, 1.0
    else:
        x0, y0, x1, y1 = bb
        minx, miny = x0 - pad, y0 - pad
        vw, vh = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{_fmt(minx, decimals)} {_fmt(miny, decimals)} '
        f'{_fmt(vw, decimals)} {_fmt(vh, decimals)}" '
        f'fill="none" stroke="{stroke}" stroke-width="{_fmt(stroke_width, decimals)}">'
    ]
    for poly in geometry.paths:
        parts.append(f'<path d="{_path_d(poly, decimals)}"/>')
    for pt in geometry.points:
        parts.append(
            f'<circle cx="{_fmt(pt.x, decimals)}" cy="{_fmt(pt.y, decimals)}" '
            f'r="{_fmt(stroke_width, decimals)}" fill="{stroke}"/>'
        )
    if geometry.unknown:
        parts.append(f"<!-- {len(geometry.unknown)} UNVERIFIABLE cells omitted -->")
    parts.append("</svg>")
    return "\n".join(parts)


def to_coords(geometry: Geometry, *, decimals: int = 2) -> str:
    """Geometry -> a compact sparse text listing (token-cheap, model-readable).
    'L'=open polyline, 'P'=closed polygon, 'pt'=isolated point; a trailing
    'unknown N' line when N>0. Empty geometry -> 'empty'."""
    lines: list[str] = []
    for poly in geometry.paths:
        tag = "P" if poly.closed else "L"
        coords = " ".join(
            f"{_fmt(p.x, decimals)},{_fmt(p.y, decimals)}" for p in poly.points
        )
        lines.append(f"{tag} {coords}")
    for pt in geometry.points:
        lines.append(f"pt {_fmt(pt.x, decimals)},{_fmt(pt.y, decimals)}")
    if geometry.unknown:
        lines.append(f"unknown {len(geometry.unknown)}")
    return "\n".join(lines) if lines else "empty"
