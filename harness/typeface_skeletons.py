"""typeface_skeletons.py: the alphabet's topology, held apart from style.

A skeleton is the centerline a pen will travel: what makes an 'n' an 'n'
regardless of weight, contrast, or width. Skeletons live in a normalized
space (y in multiples of the x-height, baseline at 0) and are sampled to
polylines here; the forge applies the pen, the rules, and the receipt.
The v1 charset is the type designer's proving word: adhesion.
"""
from __future__ import annotations

import math

# sampling density for curved strokes
_N = 48


def _superellipse(cx, cy, rx, ry, n, t0=0.0, t1=2 * math.pi, steps=_N):
    """A superellipse arc: n=2 is an ellipse, higher squares the bowl."""
    pts = []
    for i in range(steps + 1):
        t = t0 + (t1 - t0) * i / steps
        c, s = math.cos(t), math.sin(t)
        x = cx + rx * math.copysign(abs(c) ** (2.0 / n), c)
        y = cy + ry * math.copysign(abs(s) ** (2.0 / n), s)
        pts.append((x, y))
    return pts


def _line(x0, y0, x1, y1, steps=12):
    return [(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
            for i in range(steps + 1)]


def build(params: dict) -> dict:
    """Sampled centerlines per glyph. Each stroke: {pts, role, closed}.
    Units: the forge multiplies by the em; here y=1.0 is the x-height."""
    w = params["width"]                 # width factor
    n = params["roundness"]             # superellipse exponent
    ap = params["aperture"]             # 0 closed .. 1 open terminals
    asc = params.get("ascender", 1.5)   # ascender in x-heights
    ov = 0.0                            # overshoot applied by the forge

    bowl_rx = 0.52 * w
    bowl = dict(cx=bowl_rx, cy=0.5, rx=bowl_rx, ry=0.5 + ov, n=n)
    adv_round = 2 * bowl_rx
    stem_gap = 0.98 * w                 # n/h arch span
    shoulder = 0.98                     # arch peak sits just under x-height

    def bowl_ring():
        return {"pts": _superellipse(**bowl), "role": "bowl", "closed": True}

    def stem(x, y0, y1):
        return {"pts": _line(x, y0, x, y1), "role": "stem", "closed": False}

    def arch(x0, x1):
        # left stem into shoulder into right stem: a half superellipse
        cx = (x0 + x1) / 2.0
        rx = (x1 - x0) / 2.0
        pts = _superellipse(cx, 0.55, rx, shoulder - 0.55, n,
                            t0=math.pi, t1=0.0)
        return {"pts": pts, "role": "arch", "closed": False}

    g = {}

    g["i"] = {"advance": 0.30 * w + 0.0, "strokes": [
        stem(0.15 * w, 0.0, 1.0),
        {"pts": _superellipse(0.15 * w, 1.32, 0.07, 0.07, 2.0),
         "role": "dot", "closed": True}]}

    g["n"] = {"advance": stem_gap + 0.30 * w, "strokes": [
        stem(0.15 * w, 0.0, 1.0),
        arch(0.15 * w, 0.15 * w + stem_gap),
        stem(0.15 * w + stem_gap, 0.0, 0.55)]}

    g["h"] = {"advance": stem_gap + 0.30 * w, "strokes": [
        stem(0.15 * w, 0.0, asc),
        arch(0.15 * w, 0.15 * w + stem_gap),
        stem(0.15 * w + stem_gap, 0.0, 0.55)]}

    g["o"] = {"advance": adv_round, "strokes": [bowl_ring()]}

    # e: the bowl opens at the lower right; the gap follows the aperture
    _e_gap = 0.55 + 0.6 * ap
    _e_t0 = -math.pi / 4 + _e_gap / 2
    g["e"] = {"advance": adv_round, "strokes": [
        {"pts": _superellipse(bowl["cx"], 0.5, bowl_rx, 0.5, n,
                              t0=_e_t0, t1=_e_t0 + 2 * math.pi - _e_gap),
         "role": "bowl", "closed": False},
        {"pts": _line(bowl["cx"] - bowl_rx * 0.92, 0.55,
                      bowl["cx"] + bowl_rx * 0.92, 0.55),
         "role": "crossbar", "closed": False}]}

    g["d"] = {"advance": adv_round + 0.12 * w, "strokes": [
        bowl_ring(),
        stem(2 * bowl_rx - 0.02, 0.0, asc)]}

    g["a"] = {"advance": adv_round + 0.10 * w, "strokes": [  # single story
        bowl_ring(),
        stem(2 * bowl_rx - 0.02, 0.0, 1.0)]}

    # s: one continuous spine; the top bowl opens right, the bottom left,
    # curvature reversing at the waist, terminals eased by the aperture
    _s_term = 0.45 + 0.4 * ap
    _top = _superellipse(0.46 * w, 0.735, 0.30 * w, 0.265, min(n, 2.2),
                         t0=_s_term, t1=1.5 * math.pi)
    _bot = _superellipse(0.46 * w, 0.265, 0.30 * w, 0.265, min(n, 2.2),
                         t0=0.5 * math.pi, t1=-math.pi + _s_term)
    g["s"] = {"advance": 0.92 * adv_round, "strokes": [
        {"pts": _top + _bot[1:], "role": "spine", "closed": False}]}

    return g
