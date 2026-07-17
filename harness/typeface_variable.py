"""typeface_variable.py: a minted family, shipped as ONE variable font.

The family already mints the same seed at several weights, so every
instance shares its skeleton bones. That is exactly the precondition a
variable font needs: interpolation-compatible masters. This module takes
those masters, verifies the compatibility rather than assuming it (same
glyph set, same contour count, same point count per contour, in the same
order), and emits a single TrueType GX font with a `wght` axis, an `fvar`
of named instances, and a `gvar` of per-master point deltas.

The default master's outlines are the base glyf; every other master
contributes deltas. Nothing here fakes interpolation: a topology mismatch
is a named refusal, never a silently broken font.
"""
from __future__ import annotations

import struct

from .typeface_ttf import EM, _cmap, _name, _pad4, _sfnt

_EPOCH = 3849984000  # fixed timestamp, so the same masters hash the same font


def _glyph_points(face: dict, order: list) -> dict:
    """The exact point list per glyph, in glyf serialization order (contours
    in order, points within a contour in order), plus the glyph's advance.
    Mirrors typeface_ttf._glyf_entry so gvar deltas line up point-for-point."""
    out = {}
    gsrc = face["glyphs"]
    for gname in order:
        if gname in (".notdef", "space"):
            out[gname] = {"points": [], "ends": [],
                          "advance": 600 if gname == ".notdef" else 250}
            continue
        pts, ends, n = [], [], 0
        for ring in gsrc[gname]["contours"]:
            ctr = [(round(x), round(y)) for x, y in ring[:-1]]
            if len(ctr) < 3:
                continue
            pts.extend(ctr)
            n += len(ctr)
            ends.append(n - 1)
        out[gname] = {"points": pts, "ends": ends,
                      "advance": round(gsrc[gname]["advance"])}
    return out


def _compatible(masters: list) -> str | None:
    """Why these masters cannot interpolate, or None when they can."""
    order = masters[0]["order"]
    base = masters[0]["pts"]
    for m in masters[1:]:
        if m["order"] != order:
            return "masters carry different glyph sets"
        for g in order:
            if len(m["pts"][g]["points"]) != len(base[g]["points"]):
                return f"glyph {g!r} has a different point count across weights"
            if m["pts"][g]["ends"] != base[g]["ends"]:
                return f"glyph {g!r} has a different contour split across weights"
    return None


def _f2dot14(v: float) -> int:
    return max(-0x8000, min(0x7FFF, round(v * 16384)))


def _pack_deltas(vals: list) -> bytes:
    """gvar packed deltas: runs of zeros, bytes, or words."""
    out = b""
    i, n = 0, len(vals)
    while i < n:
        v = vals[i]
        if v == 0:
            j = i
            while j < n and vals[j] == 0 and j - i < 64:
                j += 1
            out += bytes([0x80 | (j - i - 1)])
            i = j
        elif -128 <= v <= 127:
            j = i
            while j < n and -128 <= vals[j] <= 127 and vals[j] != 0 \
                    and j - i < 64:
                j += 1
            out += bytes([(j - i - 1)])
            out += b"".join(struct.pack(">b", x) for x in vals[i:j])
            i = j
        else:
            j = i
            while j < n and not (-128 <= vals[j] <= 127) and j - i < 64:
                j += 1
            out += bytes([0x40 | (j - i - 1)])
            out += b"".join(struct.pack(">h", x) for x in vals[i:j])
            i = j
    return out


def _glyph_variation(base_pts, master_pts, peak, inter):
    """One glyph's GlyphVariationData across all non-default masters. base_pts
    and each master already carry their 4 phantom points, so the deltas cover
    every point including the advance; packed point count 0x00 = all points."""
    headers, datas = b"", b""
    for k, mp in enumerate(master_pts):
        dx = [mp[i][0] - base_pts[i][0] for i in range(len(base_pts))]
        dy = [mp[i][1] - base_pts[i][1] for i in range(len(base_pts))]
        body = b"\x00" + _pack_deltas(dx) + _pack_deltas(dy)  # 0x00 = all pts
        idx, s, e = peak[k], inter[k][0], inter[k][1]
        # embedded peak + intermediate region + this tuple owns its (all-)points
        flags = 0x8000 | 0x4000 | 0x2000
        hdr = struct.pack(">HH", len(body), flags)
        hdr += struct.pack(">h", _f2dot14(idx))
        hdr += struct.pack(">h", _f2dot14(s)) + struct.pack(">h", _f2dot14(e))
        headers += hdr
        datas += body
    count = len(master_pts)
    data_off = 4 + len(headers)
    return struct.pack(">HH", count, data_off) + headers + datas


def to_variable_ttf(masters: list, family: str = "Zentropy Mint") -> dict:
    """masters: list of {'weight': float, 'face': dict, 'style': str}; the
    median weight is the default. Returns {'ttf': bytes} or {'error': str}."""
    if len(masters) < 2:
        return {"error": "a variable font needs at least two masters"}
    ms = sorted(masters, key=lambda m: m["weight"])
    order = [".notdef", "space"] + sorted(ms[0]["face"]["glyphs"])
    for m in ms:
        m["order"] = order
        m["pts"] = _glyph_points(m["face"], order)
    why = _compatible(ms)
    if why:
        return {"error": why}

    lo, hi = ms[0]["weight"], ms[-1]["weight"]
    default = ms[len(ms) // 2]
    dw = default["weight"]

    def norm(w):
        if w == dw:
            return 0.0
        return (w - dw) / (hi - dw) if w > dw else (w - dw) / (dw - lo)

    others = [m for m in ms if m is not default]
    coords = [norm(m["weight"]) for m in others]
    # each non-default master peaks at its coord; the region spans to the
    # adjacent master coords (0 toward the default), so masters don't bleed
    peaks, inters = [], []
    negs = sorted(c for c in coords if c < 0)
    poss = sorted(c for c in coords if c > 0)
    for c in coords:
        if c < 0:
            below = [x for x in negs if x < c]
            peaks_start = max(below) if below else -1.0
            inters.append((peaks_start, 0.0))
        else:
            above = [x for x in poss if x > c]
            peaks_end = min(above) if above else 1.0
            inters.append((0.0, peaks_end))
        peaks.append(c)

    # glyf + loca + hmtx from the DEFAULT master's outlines
    from .typeface_ttf import _glyf_entry
    glyf, loca, hmtx = b"", [0], []
    gpts_default = default["pts"]
    gxmin = gymin = 32767
    gxmax = gymax = -32768
    max_pts = max_ctrs = 0
    for g in order:
        gp = gpts_default[g]
        if not gp["points"]:
            hmtx.append((gp["advance"], 0))
            loca.append(len(glyf))
            continue
        contours, k = [], 0
        for end in gp["ends"]:
            contours.append(gp["points"][k:end + 1])
            k = end + 1
        entry, (x0, y0, x1, y1), npts, nctr = _glyf_entry(contours)
        glyf += _pad4(entry)
        loca.append(len(glyf))
        hmtx.append((gp["advance"], x0))
        gxmin, gymin = min(gxmin, x0), min(gymin, y0)
        gxmax, gymax = max(gxmax, x1), max(gymax, y1)
        max_pts, max_ctrs = max(max_pts, npts), max(max_ctrs, nctr)

    n = len(order)
    ascent, descent = max(gymax + 60, 900), min(gymin - 40, -180)
    head = struct.pack(">LLLLHHQQhhhhHHhhh",
                       0x00010000, 0x00010000, 0, 0x5F0F3CF5, 0b11, EM,
                       _EPOCH, _EPOCH, gxmin, gymin, gxmax, gymax, 0, 8,
                       1, 1, 0)  # indexToLocFormat=1 (long loca)
    hhea = struct.pack(">LhhhHhhhhhhhhhhhH", 0x00010000, ascent, descent, 0,
                       max(a for a, _ in hmtx), min(l for _, l in hmtx),
                       0, gxmax, 1, 0, 0, 0, 0, 0, 0, 0, n)
    maxp = struct.pack(">LHHHHHHHHHHHHHH", 0x00010000, n, max_pts + 4,
                       max_ctrs, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0)
    hmtx_b = b"".join(struct.pack(">Hh", a, l) for a, l in hmtx)
    loca_b = struct.pack(f">{len(loca)}L", *loca)

    # fvar: one wght axis (user coords are OS/2-style usWeightClass) + a
    # named instance per master. The axis min/def/max are Fixed (16.16).
    def uweight(w):
        return max(1, min(1000, round(w * 4706)))
    # fvar header: major, minor, axesArrayOffset=16, reserved=2, axisCount=1,
    # axisSize=20, instanceCount, instanceSize=8 (subfamilyID + flags + 1 coord)
    fvar = struct.pack(">HHHHHHHH", 1, 0, 16, 2, 1, 20, len(ms), 8)
    fvar += struct.pack(">4slllHH", b"wght", _fix(uweight(lo)),
                        _fix(uweight(dw)), _fix(uweight(hi)), 0, 1)
    name_extra = []
    for i, m in enumerate(ms):
        nameid = 256 + i
        fvar += struct.pack(">HHl", nameid, 0, _fix(uweight(m["weight"])))
        name_extra.append((nameid, m["style"]))

    gvar = _build_gvar(order, gpts_default, [m["pts"] for m in others],
                       peaks, inters)

    tables = {b"cmap": _cmap({32: 1, **{ord(c): 2 + i for i, c in
              enumerate(sorted(ms[0]["face"]["glyphs"]))}}),
              b"glyf": glyf, b"head": head, b"hhea": hhea, b"hmtx": hmtx_b,
              b"loca": loca_b, b"maxp": maxp,
              b"name": _name(family, "Regular", extra=name_extra),
              b"post": struct.pack(">LLhhLLLLLL", 0x00030000, 0, -75, 50,
                                   0, 0, 0, 0, 0, 0),
              b"fvar": fvar, b"gvar": gvar}
    return {"ttf": _sfnt(tables)}


def _fix(v: float) -> int:
    return max(-0x80000000, min(0x7FFFFFFF, round(v * 65536)))


def _build_gvar(order, base, other_pts, peaks, inters):
    """The gvar table: one GlyphVariationData per glyph, long (32-bit)
    offsets so a large family never overflows."""
    glyph_data, offsets = b"", [0]
    for g in order:
        if not base[g]["points"]:
            offsets.append(len(glyph_data))     # empty glyph: no variation
            continue
        bp = base[g]["points"] + [(0, 0), (base[g]["advance"], 0),
                                  (0, 0), (0, 0)]
        mps = [op[g]["points"] + [(0, 0), (op[g]["advance"], 0),
                                  (0, 0), (0, 0)] for op in other_pts]
        glyph_data += _pad4(_glyph_variation(bp, mps, peaks, inters))
        offsets.append(len(glyph_data))
    n = len(order)
    data_off = 20 + 4 * (n + 1)      # header(20) + offsets array
    hdr = struct.pack(">HHHHLHHL", 1, 0, 1, 0, 0, n, 0x0001, data_off)
    hdr += struct.pack(f">{len(offsets)}L", *offsets)
    return hdr + glyph_data
