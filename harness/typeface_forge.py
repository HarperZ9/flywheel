"""typeface_forge.py: parametric type under witness.

A face here is a deterministic artifact. A seed and a parameter set expand
fixed skeletons (the alphabet's topology) through a pen model (the stroke:
width varying with direction, after Noordzij) into outlines, and the
legibility invariants run as rules that can REFUSE the mint: a counter
that closes or a contrast that blinds is a named refusal, never a shrug.
The receipt binds seed, parameters, skeleton library, and engine source,
so the same inputs always mint the same face and originality is
re-derivable instead of asserted."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from . import typeface_skeletons

EM = 1000.0

DEFAULTS = {
    "x_height": 0.50,    # of the em
    "ascender": 1.5,     # in x-heights
    "weight": 0.085,     # stem width, of the em
    "contrast": 0.82,    # horizontal/vertical stroke ratio (1 = monolinear)
    "width": 1.0,        # condensed .. extended
    "roundness": 2.4,    # superellipse exponent for bowls
    "aperture": 0.6,     # 0 closed .. 1 open terminals
    "overshoot": 0.015,  # of the x-height, on round extremes
}

RULES = ("overshoot", "contrast-floor", "counter-minimum", "tracy-spacing")


def _mulberry32(seed: int):
    a = seed & 0xFFFFFFFF

    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = a
        t = (t ^ (t >> 15)) * (t | 1) & 0xFFFFFFFF
        t = (t ^ (t + ((t ^ (t >> 7)) * (t | 61) & 0xFFFFFFFF))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return rnd


def _pen_width(dx, dy, w_v, contrast):
    """The stroke: a vertical move lays the full nib, a horizontal move the
    thin side, everything between follows the ellipse of the pen."""
    L = math.hypot(dx, dy) or 1.0
    vertical = abs(dy) / L
    return w_v * (contrast + (1.0 - contrast) * vertical)


def _expand(pts, closed, w_v, contrast):
    """Centerline -> closed ink ring(s) by normal offset."""
    n = len(pts)
    ring_in = closed and pts[0] == pts[-1]
    left, right = [], []
    for i, (x, y) in enumerate(pts):
        if ring_in:  # wrapped neighbors: no seam notch at the joint
            x0, y0 = pts[(i - 1) % (n - 1)]
            x1, y1 = pts[(i + 1) % (n - 1)]
        else:
            x0, y0 = pts[max(0, i - 1)]
            x1, y1 = pts[min(n - 1, i + 1)]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        w = _pen_width(dx, dy, w_v, contrast) / 2.0
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    if closed:
        outer = left + [left[0]]
        inner = list(reversed(right)) + [right[-1]]
        return [outer, inner]
    ring = left + list(reversed(right))
    ring.append(ring[0])
    return [ring]


def _round(pts):
    return [(round(x, 2), round(y, 2)) for x, y in pts]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mint(params: dict, seed: int = 0) -> dict:
    p = {**DEFAULTS, **(params or {})}
    rnd = _mulberry32(int(seed))
    # seeded micro-variation inside legibility bounds: the face's signature
    p["_shoulder_jitter"] = round((rnd() - 0.5) * 0.02, 5)
    p["_terminal_jitter"] = round((rnd() - 0.5) * 0.06, 5)

    xh = p["x_height"] * EM
    w_v = p["weight"] * EM
    w_h = w_v * p["contrast"]
    skeletons = typeface_skeletons.build(p)

    refusals = []
    # counter-minimum: the bowl must keep daylight once the pen is laid
    bowl_rx = 0.52 * p["width"] * xh
    counter_w = 2.0 * (bowl_rx - w_v)
    if counter_w < 0.30 * xh:
        refusals.append(
            f"counter-minimum: bowl counter {counter_w:.0f} under "
            f"{0.30 * xh:.0f} em-units; lighten the weight or raise the "
            f"x-height")
    # contrast-floor: below this the horizontals vanish at text sizes
    if p["contrast"] < 0.45:
        refusals.append("contrast-floor: horizontals thinner than 0.45 of "
                        "the stem blind the eye at text sizes")

    here = Path(__file__).resolve()
    receipt = {
        "schema": "flywheel.typeface-mint/v1",
        "seed": int(seed),
        "params": {k: v for k, v in sorted(p.items())},
        "engine_sha256": _sha(here),
        "skeletons_sha256": _sha(here.with_name("typeface_skeletons.py")),
        "rules_applied": list(RULES),
        "charset": sorted(skeletons),
    }
    receipt["mint_id"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True).encode()).hexdigest()[:16]

    if refusals:
        return {"refused": True, "refusals": refusals, "receipt": receipt,
                "glyphs": {}, "svg": ""}

    glyphs = {}
    for name, spec in skeletons.items():
        contours = []
        for stroke in spec["strokes"]:
            pts = [(x * xh, y * xh) for x, y in stroke["pts"]]
            if stroke["role"] in ("bowl", "dot", "spine"):
                # overshoot: round extremes reach past the line to look even
                pts = [(x, y * (1.0 + p["overshoot"])) for x, y in pts]
            for ring in _expand(pts, stroke["closed"], w_v, p["contrast"]):
                contours.append(_round(ring))
        top = max(y for c in contours for _, y in c)
        # tracy-spacing: straight sides earn the full bearing, round sides
        # tuck in because their white leaks into the counter rhythm
        straight = any(s["role"] == "stem" for s in spec["strokes"])
        base_lsb = 0.22 * w_v + 0.05 * xh
        lsb = round(base_lsb if straight else base_lsb * 0.82, 2)
        glyphs[name] = {
            "contours": contours,
            "advance": round(spec["advance"] * xh + 2 * lsb, 2),
            "lsb": lsb,
            "top": round(top, 2),
            "v_stroke": round(w_v, 2),
            "h_stroke": round(w_h, 2),
        }

    return {"refused": False, "refusals": [], "receipt": receipt,
            "glyphs": glyphs, "metrics": {"em": EM, "x_height": xh},
            "svg": _specimen(glyphs, xh)}


def _specimen(glyphs: dict, xh: float) -> str:
    """The proving word, drawn from the minted outlines."""
    word = "adhesion"
    x, parts = 40.0, []
    H = 2.2 * xh
    for ch in word:
        g = glyphs.get(ch)
        if g is None:
            continue
        # every contour of the glyph in ONE path, so nonzero winding welds
        # overlapping strokes and carves the counters by orientation
        subpaths = []
        for ring in g["contours"]:
            subpaths.append("M " + " L ".join(
                f"{x + px:.1f} {H - py:.1f}" for px, py in ring) + " Z")
        parts.append(f'<path d="{" ".join(subpaths)}" fill="currentColor" '
                     f'fill-rule="nonzero"/>')
        x += g["advance"]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {x + 40:.0f} {H + 60:.0f}">'
            + "".join(parts) + "</svg>")
