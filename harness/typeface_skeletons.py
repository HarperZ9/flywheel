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
        stem(0.15 * w + stem_gap, 0.0, 0.62)]}

    g["h"] = {"advance": stem_gap + 0.30 * w, "strokes": [
        stem(0.15 * w, 0.0, asc),
        arch(0.15 * w, 0.15 * w + stem_gap),
        stem(0.15 * w + stem_gap, 0.0, 0.62)]}

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

    desc = -0.45                          # descender depth in x-heights

    def diag(x0, y0, x1, y1):
        return {"pts": _line(x0, y0, x1, y1), "role": "diag", "closed": False}

    g["b"] = {"advance": adv_round + 0.12 * w, "strokes": [
        stem(0.02, 0.0, asc), bowl_ring()]}

    g["p"] = {"advance": adv_round + 0.12 * w, "strokes": [
        stem(0.02, desc, 1.0), bowl_ring()]}

    g["q"] = {"advance": adv_round + 0.12 * w, "strokes": [
        bowl_ring(), stem(2 * bowl_rx - 0.02, desc, 1.0)]}

    # g: the single-story form; bowl plus a descender that hooks left
    _g_hook = _superellipse(2 * bowl_rx - 0.02 - 0.26 * w, desc + 0.22,
                            0.26 * w, 0.22, min(n, 2.2),
                            t0=0.0, t1=-math.pi + 0.4)
    g["g"] = {"advance": adv_round + 0.12 * w, "strokes": [
        bowl_ring(),
        stem(2 * bowl_rx - 0.02, desc + 0.20, 1.0),
        {"pts": _g_hook, "role": "tail", "closed": False}]}

    # c: the open bowl, gap centered on the right
    _c_gap = 0.75 + 0.5 * ap
    g["c"] = {"advance": adv_round, "strokes": [
        {"pts": _superellipse(bowl["cx"], 0.5, bowl_rx, 0.5, n,
                              t0=_c_gap / 2, t1=2 * math.pi - _c_gap / 2),
         "role": "bowl", "closed": False}]}

    g["l"] = {"advance": 0.30 * w, "strokes": [stem(0.15 * w, 0.0, asc)]}

    # f: ascender stem with a rightward hook, crossbar at the x-height
    _f_hook = _superellipse(0.15 * w + 0.24 * w, asc - 0.24, 0.24 * w, 0.24,
                            min(n, 2.2), t0=math.pi, t1=0.5 * math.pi)
    g["f"] = {"advance": 0.52 * w, "strokes": [
        stem(0.15 * w, 0.0, asc - 0.24),
        {"pts": list(reversed(_f_hook)), "role": "hook", "closed": False},
        {"pts": _line(-0.02, 1.0, 0.44 * w, 1.0),
         "role": "crossbar", "closed": False}]}

    # t: a taller stem than the x-height, crossbar riding the line
    g["t"] = {"advance": 0.52 * w, "strokes": [
        stem(0.15 * w, 0.0, 1.28),
        {"pts": _line(-0.02, 1.0, 0.44 * w, 1.0),
         "role": "crossbar", "closed": False}]}

    # j: a stem falling past the baseline into a left hook, dotted
    _j_hook = _superellipse(0.15 * w - 0.22 * w, desc + 0.20, 0.22 * w, 0.20,
                            min(n, 2.2), t0=0.0, t1=-math.pi + 0.5)
    g["j"] = {"advance": 0.34 * w, "strokes": [
        stem(0.15 * w, desc + 0.18, 1.0),
        {"pts": _j_hook, "role": "tail", "closed": False},
        {"pts": _superellipse(0.15 * w, 1.32, 0.07, 0.07, 2.0),
         "role": "dot", "closed": True}]}

    g["k"] = {"advance": 0.92 * w + 0.2 * w, "strokes": [
        stem(0.15 * w, 0.0, asc),
        diag(0.15 * w, 0.42, 0.15 * w + 0.72 * w, 1.0),
        diag(0.15 * w + 0.26 * w, 0.60, 0.15 * w + 0.78 * w, 0.0)]}

    # m: one stem, two half-width arches, the n twice over
    _m_gap = 0.62 * w
    g["m"] = {"advance": 2 * _m_gap + 0.30 * w, "strokes": [
        stem(0.15 * w, 0.0, 1.0),
        arch(0.15 * w, 0.15 * w + _m_gap),
        stem(0.15 * w + _m_gap, 0.0, 0.62),
        arch(0.15 * w + _m_gap, 0.15 * w + 2 * _m_gap),
        stem(0.15 * w + 2 * _m_gap, 0.0, 0.62)]}

    # r: the stem and just the shoulder of an arch
    _r_arc = _superellipse(0.15 * w + 0.38 * w, 0.60, 0.38 * w, 0.38, n,
                           t0=math.pi, t1=0.35 * math.pi)
    g["r"] = {"advance": 0.62 * w, "strokes": [
        stem(0.15 * w, 0.0, 1.0),
        {"pts": _r_arc, "role": "arch", "closed": False}]}

    # u: the n turned over: stems falling into a bottom arch
    _u_arc = _superellipse((0.3 * w + stem_gap) / 2 + 0.0, 0.45,
                           stem_gap / 2, 0.43, n,
                           t0=math.pi, t1=2 * math.pi)
    g["u"] = {"advance": stem_gap + 0.30 * w, "strokes": [
        stem(0.15 * w, 0.45, 1.0),
        {"pts": [(x + 0.15 * w - ((0.3 * w + stem_gap) / 2 - stem_gap / 2),
                  y) for x, y in _u_arc],
         "role": "arch", "closed": False},
        stem(0.15 * w + stem_gap, 0.0, 1.0)]}

    g["v"] = {"advance": 1.04 * w, "strokes": [
        diag(0.02, 1.0, 0.52 * w, 0.0), diag(0.52 * w, 0.0, 1.02 * w, 1.0)]}

    g["w"] = {"advance": 1.46 * w, "strokes": [
        diag(0.02, 1.0, 0.38 * w, 0.0), diag(0.38 * w, 0.0, 0.72 * w, 0.92),
        diag(0.72 * w, 0.92, 1.06 * w, 0.0), diag(1.06 * w, 0.0, 1.42 * w, 1.0)]}

    g["x"] = {"advance": 1.0 * w, "strokes": [
        diag(0.02, 1.0, 0.98 * w, 0.0), diag(0.02, 0.0, 0.98 * w, 1.0)]}

    # y: a v whose right side keeps falling
    g["y"] = {"advance": 1.04 * w, "strokes": [
        diag(0.02, 1.0, 0.52 * w, 0.0),
        diag(1.02 * w, 1.0, 0.52 * w + desc * (-0.5 * w / 1.0) * -1, desc)]}

    g["z"] = {"advance": 0.94 * w, "strokes": [
        {"pts": _line(0.04, 1.0, 0.90 * w, 1.0),
         "role": "crossbar", "closed": False},
        diag(0.90 * w, 1.0, 0.04, 0.0),
        {"pts": _line(0.04, 0.0, 0.90 * w, 0.0),
         "role": "crossbar", "closed": False}]}

    # digits: figure height rides above the x-height, one style DNA
    fh = 1.28                      # figure height in x-heights
    dr = 0.40 * w                  # digit bowl radius
    dcx = dr + 0.02

    def dbowl(cy, ry, t0=0.0, t1=2 * math.pi):
        return {"pts": _superellipse(dcx, cy, dr, ry, n, t0=t0, t1=t1),
                "role": "bowl", "closed": abs((t1 - t0) - 2 * math.pi) < 1e-9}

    g["0"] = {"advance": 2 * dr + 0.04, "strokes": [
        {"pts": _superellipse(dcx, fh / 2, dr, fh / 2, n),
         "role": "bowl", "closed": True}]}

    g["1"] = {"advance": 0.46 * w, "strokes": [
        stem(0.30 * w, 0.0, fh),
        diag(0.10 * w, fh - 0.22, 0.30 * w, fh)]}

    # 2: the shoulder sweeps clockwise over the top, falls to the corner,
    # and the bar closes the floor
    _2_arc = _superellipse(0.42 * w, fh - 0.36, 0.38 * w, 0.36,
                           min(n, 2.2), t0=0.85 * math.pi,
                           t1=-0.25 * math.pi)
    _2_spine = _2_arc + _line(_2_arc[-1][0], _2_arc[-1][1], 0.06 * w, 0.0)[1:]
    g["2"] = {"advance": 0.88 * w, "strokes": [
        {"pts": _2_spine, "role": "spine", "closed": False},
        {"pts": _line(0.06 * w, 0.0, 0.84 * w, 0.0),
         "role": "crossbar", "closed": False}]}

    # 3: two right-opening arcs meeting at the waist, both clockwise
    g["3"] = {"advance": 0.86 * w, "strokes": [
        {"pts": _superellipse(0.40 * w, fh - 0.33, 0.34 * w, 0.33,
                              min(n, 2.2), t0=0.80 * math.pi,
                              t1=-0.45 * math.pi),
         "role": "bowl", "closed": False},
        {"pts": _superellipse(0.40 * w, 0.36, 0.38 * w, 0.36,
                              min(n, 2.2), t0=0.52 * math.pi,
                              t1=-0.85 * math.pi),
         "role": "bowl", "closed": False}]}

    g["4"] = {"advance": 0.92 * w, "strokes": [
        diag(0.58 * w, fh, 0.04, 0.38),
        {"pts": _line(0.04, 0.38, 0.86 * w, 0.38),
         "role": "crossbar", "closed": False},
        stem(0.58 * w, 0.0, fh)]}

    # 5: flag, flagpole, then a clockwise bowl opening back to the left
    g["5"] = {"advance": 0.86 * w, "strokes": [
        {"pts": _line(0.72 * w, fh, 0.10 * w, fh),
         "role": "crossbar", "closed": False},
        stem(0.10 * w, fh - 0.52, fh),
        {"pts": _superellipse(0.38 * w, 0.40, 0.40 * w, 0.40,
                              min(n, 2.2), t0=0.70 * math.pi,
                              t1=-0.90 * math.pi),
         "role": "bowl", "closed": False}]}

    g["6"] = {"advance": 0.88 * w, "strokes": [
        {"pts": _superellipse(0.42 * w, 0.40, 0.40 * w, 0.40, n),
         "role": "bowl", "closed": True},
        {"pts": _superellipse(0.52 * w, fh - 0.52, 0.50 * w, 0.52,
                              min(n, 2.2), t0=0.55 * math.pi,
                              t1=1.0 * math.pi),
         "role": "spine", "closed": False}]}

    g["7"] = {"advance": 0.84 * w, "strokes": [
        {"pts": _line(0.04, fh, 0.80 * w, fh),
         "role": "crossbar", "closed": False},
        diag(0.80 * w, fh, 0.26 * w, 0.0)]}

    g["8"] = {"advance": 0.88 * w, "strokes": [
        {"pts": _superellipse(0.42 * w, fh - 0.31, 0.34 * w, 0.31, n),
         "role": "bowl", "closed": True},
        {"pts": _superellipse(0.42 * w, 0.36, 0.40 * w, 0.36, n),
         "role": "bowl", "closed": True}]}

    g["9"] = {"advance": 0.88 * w, "strokes": [
        {"pts": _superellipse(0.42 * w, fh - 0.40, 0.40 * w, 0.40, n),
         "role": "bowl", "closed": True},
        {"pts": _superellipse(0.32 * w, 0.52, 0.50 * w, 0.52,
                              min(n, 2.2), t0=-0.45 * math.pi,
                              t1=0.0)},
         ]}

    g["9"]["strokes"][1]["role"] = "spine"
    g["9"]["strokes"][1]["closed"] = False

    # the minimum punctuation a working face owes its user
    g["."] = {"advance": 0.26 * w, "strokes": [
        {"pts": _superellipse(0.13 * w, 0.075, 0.075, 0.075, 2.0),
         "role": "dot", "closed": True}]}

    g[","] = {"advance": 0.26 * w, "strokes": [
        {"pts": _superellipse(0.13 * w, 0.075, 0.075, 0.075, 2.0),
         "role": "dot", "closed": True},
        {"pts": _line(0.13 * w, 0.0, 0.06 * w, -0.16),
         "role": "tail", "closed": False}]}

    g["-"] = {"advance": 0.52 * w, "strokes": [
        {"pts": _line(0.06 * w, 0.5, 0.46 * w, 0.5),
         "role": "crossbar", "closed": False}]}

    # ---- uppercase: the caps ride to the cap line on their own proportions.
    # Same pen, same roles; a cap is a stem, a bowl, a diagonal, or a bar
    # reaching y=C instead of the x-height. Small caps are these, set small.
    C = 1.40                            # cap height in x-heights (under the asc)
    cs = 0.02                           # left bearing origin; ink shifts to lsb
    crx = 0.50 * w                      # round-cap bowl radius

    def cbar(x0, x1, y):
        return {"pts": _line(x0, y, x1, y), "role": "crossbar", "closed": False}

    def cring(cx, rx):                  # a full cap bowl (O, Q)
        return {"pts": _superellipse(cx, C / 2, rx, C / 2, n),
                "role": "bowl", "closed": True}

    def crhalf(cy, ry, rx):            # a right-opening half bowl (B, P, R lobes)
        return {"pts": _superellipse(cs, cy, rx, ry, min(n, 2.4),
                                     t0=0.5 * math.pi, t1=-0.5 * math.pi),
                "role": "bowl", "closed": False}

    g["A"] = {"advance": 0.94 * w, "strokes": [
        diag(cs, 0.0, 0.46 * w, C), diag(0.46 * w, C, 0.92 * w, 0.0),
        cbar(0.17 * w, 0.75 * w, 0.42 * C)]}

    g["B"] = {"advance": 0.86 * w, "strokes": [
        stem(cs, 0.0, C),
        crhalf(C * 0.74, C * 0.26, 0.44 * w),
        crhalf(C * 0.26, C * 0.26, 0.50 * w)]}

    g["C"] = {"advance": 0.92 * w, "strokes": [
        {"pts": _superellipse(crx + cs, C / 2, crx, C / 2, n,
                              t0=0.30 * math.pi,
                              t1=2 * math.pi - 0.30 * math.pi),
         "role": "bowl", "closed": False}]}

    g["D"] = {"advance": 0.98 * w, "strokes": [
        stem(cs, 0.0, C),
        {"pts": _superellipse(cs, C / 2, 0.88 * w, C / 2, n,
                              t0=0.5 * math.pi, t1=-0.5 * math.pi),
         "role": "bowl", "closed": False}]}

    g["E"] = {"advance": 0.80 * w, "strokes": [
        stem(cs, 0.0, C), cbar(cs, 0.74 * w, C),
        cbar(cs, 0.64 * w, C / 2), cbar(cs, 0.74 * w, 0.0)]}

    g["F"] = {"advance": 0.76 * w, "strokes": [
        stem(cs, 0.0, C), cbar(cs, 0.74 * w, C), cbar(cs, 0.64 * w, C / 2)]}

    g["G"] = {"advance": 1.0 * w, "strokes": [
        {"pts": _superellipse(crx + cs, C / 2, crx, C / 2, n,
                              t0=0.30 * math.pi,
                              t1=2 * math.pi - 0.06 * math.pi),
         "role": "bowl", "closed": False},
        stem(2 * crx + cs - 0.02, 0.0, C * 0.46),
        cbar(0.60 * w, 2 * crx + cs, C * 0.46)]}

    g["H"] = {"advance": 0.94 * w, "strokes": [
        stem(cs, 0.0, C), stem(0.90 * w, 0.0, C), cbar(cs, 0.90 * w, C / 2)]}

    g["I"] = {"advance": 0.30 * w, "strokes": [stem(0.14 * w, 0.0, C)]}

    g["J"] = {"advance": 0.72 * w, "strokes": [
        stem(0.56 * w, C * 0.30, C),
        {"pts": _superellipse(0.28 * w, C * 0.30, 0.28 * w, 0.30,
                              min(n, 2.2), t0=0.0, t1=-math.pi),
         "role": "tail", "closed": False}]}

    g["K"] = {"advance": 0.92 * w, "strokes": [
        stem(cs, 0.0, C),
        diag(cs + 0.04, C * 0.50, 0.86 * w, C),
        diag(cs + 0.20 * w, C * 0.58, 0.90 * w, 0.0)]}

    g["L"] = {"advance": 0.74 * w, "strokes": [
        stem(cs, 0.0, C), cbar(cs, 0.72 * w, 0.0)]}

    g["M"] = {"advance": 1.30 * w, "strokes": [
        stem(cs, 0.0, C), diag(cs, C, 0.64 * w, C * 0.34),
        diag(0.64 * w, C * 0.34, 1.26 * w, C), stem(1.26 * w, 0.0, C)]}

    g["N"] = {"advance": 0.98 * w, "strokes": [
        stem(cs, 0.0, C), diag(cs, C, 0.92 * w, 0.0), stem(0.92 * w, 0.0, C)]}

    g["O"] = {"advance": 1.0 * w, "strokes": [cring(0.50 * w, 0.50 * w)]}

    g["P"] = {"advance": 0.82 * w, "strokes": [
        stem(cs, 0.0, C), crhalf(C * 0.72, C * 0.28, 0.46 * w)]}

    g["Q"] = {"advance": 1.0 * w, "strokes": [
        cring(0.50 * w, 0.50 * w),
        diag(0.56 * w, C * 0.30, 0.98 * w, -0.12)]}

    g["R"] = {"advance": 0.90 * w, "strokes": [
        stem(cs, 0.0, C), crhalf(C * 0.72, C * 0.28, 0.46 * w),
        diag(0.40 * w, C * 0.44, 0.92 * w, 0.0)]}

    _S_term = 0.45 + 0.4 * ap
    _S_top = _superellipse(0.48 * w, C * 0.735, 0.40 * w, C * 0.265,
                           min(n, 2.2), t0=_S_term, t1=1.5 * math.pi)
    _S_bot = _superellipse(0.48 * w, C * 0.265, 0.40 * w, C * 0.265,
                           min(n, 2.2), t0=0.5 * math.pi,
                           t1=-math.pi + _S_term)
    g["S"] = {"advance": 0.92 * w, "strokes": [
        {"pts": _S_top + _S_bot[1:], "role": "spine", "closed": False}]}

    g["T"] = {"advance": 0.86 * w, "strokes": [
        cbar(cs, 0.84 * w, C), stem(0.43 * w, 0.0, C)]}

    g["U"] = {"advance": 0.94 * w, "strokes": [
        stem(cs, C * 0.28, C),
        {"pts": _superellipse(0.46 * w, C * 0.28, 0.46 * w - cs, C * 0.28,
                              n, t0=math.pi, t1=2 * math.pi),
         "role": "arch", "closed": False},
        stem(0.92 * w - cs, C * 0.28, C)]}

    g["V"] = {"advance": 0.94 * w, "strokes": [
        diag(cs, C, 0.47 * w, 0.0), diag(0.47 * w, 0.0, 0.92 * w, C)]}

    g["W"] = {"advance": 1.40 * w, "strokes": [
        diag(cs, C, 0.36 * w, 0.0), diag(0.36 * w, 0.0, 0.69 * w, C * 0.86),
        diag(0.69 * w, C * 0.86, 1.02 * w, 0.0),
        diag(1.02 * w, 0.0, 1.38 * w, C)]}

    g["X"] = {"advance": 0.94 * w, "strokes": [
        diag(cs, C, 0.92 * w, 0.0), diag(cs, 0.0, 0.92 * w, C)]}

    g["Y"] = {"advance": 0.92 * w, "strokes": [
        diag(cs, C, 0.46 * w, C * 0.52), diag(0.90 * w, C, 0.46 * w, C * 0.52),
        stem(0.46 * w, 0.0, C * 0.52)]}

    g["Z"] = {"advance": 0.88 * w, "strokes": [
        cbar(cs, 0.86 * w, C), diag(0.86 * w, C, cs, 0.0),
        cbar(cs, 0.86 * w, 0.0)]}

    # ---- runic style: carved caps after the Elder Futhark hand. Runes were
    # cut, not written, so the round bowls become straight-line facets and
    # triangular lobes (Berkanan's B, Raidho's R), the circle a diamond
    # (Ingwaz), the S a Sowilo zig-zag. The already-diagonal caps keep their
    # forms; the result reads Latin but is cut, not drawn. Modern, not costume:
    # one even weight, balanced, legible. Small caps for rhinoCase are these.
    if params.get("style") == "runic":
        def _poly(points, role="bowl", closed=False):
            pts = [points[0]]
            for i in range(1, len(points)):
                pts.extend(_line(points[i - 1][0], points[i - 1][1],
                                 points[i][0], points[i][1], 4)[1:])
            return {"pts": pts, "role": role, "closed": closed}

        def tri(y0, y1, tip):          # a right-pointing triangular lobe
            return _poly([(cs, y1), (tip, (y0 + y1) / 2.0), (cs, y0)])

        g["B"] = {"advance": 0.86 * w, "strokes": [
            stem(cs, 0.0, C), tri(C * 0.52, C, 0.60 * w),
            tri(0.0, C * 0.50, 0.68 * w)]}
        g["D"] = {"advance": 0.96 * w, "strokes": [
            stem(cs, 0.0, C), _poly([(cs, C), (0.94 * w, C / 2), (cs, 0.0)])]}
        g["P"] = {"advance": 0.82 * w, "strokes": [
            stem(cs, 0.0, C), tri(C * 0.52, C, 0.58 * w)]}
        g["R"] = {"advance": 0.90 * w, "strokes": [
            stem(cs, 0.0, C), tri(C * 0.52, C, 0.58 * w),
            diag(0.30 * w, C * 0.52, 0.92 * w, 0.0)]}
        g["C"] = {"advance": 0.90 * w, "strokes": [_poly(
            [(0.86 * w, C), (0.16 * w, C * 0.74), (0.16 * w, C * 0.26),
             (0.86 * w, 0.0)])]}
        g["G"] = {"advance": 0.98 * w, "strokes": [_poly(
            [(0.86 * w, C), (0.16 * w, C * 0.74), (0.16 * w, C * 0.26),
             (0.86 * w, 0.0), (0.86 * w, C * 0.42), (0.52 * w, C * 0.42)])]}
        g["O"] = {"advance": 1.0 * w, "strokes": [_poly(
            [(0.50 * w, C), (0.98 * w, C / 2), (0.50 * w, 0.0),
             (0.02 * w, C / 2), (0.50 * w, C)], closed=True)]}
        g["Q"] = {"advance": 1.0 * w, "strokes": [
            _poly([(0.50 * w, C), (0.98 * w, C / 2), (0.50 * w, 0.0),
                   (0.02 * w, C / 2), (0.50 * w, C)], closed=True),
            diag(0.58 * w, C * 0.30, 0.98 * w, -0.14)]}
        g["S"] = {"advance": 0.88 * w, "strokes": [_poly(
            [(0.80 * w, C * 0.98), (0.16 * w, C * 0.66),
             (0.80 * w, C * 0.34), (0.16 * w, C * 0.02)], role="spine")]}
        g["J"] = {"advance": 0.70 * w, "strokes": [
            stem(0.56 * w, C * 0.20, C),
            _poly([(0.56 * w, C * 0.20), (0.30 * w, 0.0), (0.06 * w, C * 0.20)],
                  role="tail")]}
        g["U"] = {"advance": 0.94 * w, "strokes": [_poly(
            [(cs, C), (cs, C * 0.22), (0.46 * w, 0.0), (0.92 * w, C * 0.22),
             (0.92 * w, C)], role="arch")]}

    return g
