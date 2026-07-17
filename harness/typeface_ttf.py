"""typeface_ttf.py: minted outlines become an installable font file.

A TrueType font, written table by table from the standard library, with
no curve fitting: the forge's polygon rings are valid TrueType contours
(every point on-curve), so the file carries exactly the outlines the
rules approved. Deterministic by construction: the same face bytes in,
the same font bytes out, timestamps pinned, vendor ZLAB.
"""
from __future__ import annotations

import struct

EM = 1000
_EPOCH = 3768211200          # 2023-06-01 in longdatetime units, pinned


def _pad4(b: bytes) -> bytes:
    return b + b"\0" * (-len(b) % 4)


def _checksum(b: bytes) -> int:
    b = _pad4(b)
    return sum(struct.unpack(f">{len(b) // 4}I", b)) & 0xFFFFFFFF


def _glyf_entry(contours: "list[list[tuple[int, int]]]") -> bytes:
    xs = [x for c in contours for x, _ in c]
    ys = [y for c in contours for _, y in c]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    out = struct.pack(">hhhhh", len(contours), xmin, ymin, xmax, ymax)
    ends, n = [], 0
    for c in contours:
        n += len(c)
        ends.append(n - 1)
    out += struct.pack(f">{len(ends)}H", *ends)
    out += struct.pack(">H", 0)                      # no instructions
    flags = b"\x01" * n                              # every point on-curve
    out += flags
    px = 0
    xb = b""
    for c in contours:
        for x, _ in c:
            xb += struct.pack(">h", x - px)
            px = x
    py = 0
    yb = b""
    for c in contours:
        for _, y in c:
            yb += struct.pack(">h", y - py)
            py = y
    return out + xb + yb, (xmin, ymin, xmax, ymax), n, len(contours)


def _cmap(table_map: "dict[int, int]") -> bytes:
    codes = sorted(table_map)
    segs = [(c, c, table_map[c]) for c in codes] + [(0xFFFF, 0xFFFF, None)]
    seg_count = len(segs)
    sc2 = seg_count * 2
    import math
    search = 2 ** int(math.log2(seg_count)) * 2
    sub = struct.pack(">HHHHHHH", 4, 0, 16 + sc2 * 4, sc2, search,
                      int(math.log2(search // 2)), sc2 - search)
    sub += struct.pack(f">{seg_count}H", *[e for _, e, _ in segs])
    sub += struct.pack(">H", 0)                      # reservedPad
    sub += struct.pack(f">{seg_count}H", *[s for s, _, _ in segs])
    deltas = [((g - s) & 0xFFFF) if g is not None else 1
              for s, _, g in segs]
    sub += struct.pack(f">{seg_count}h",
                       *[d - 0x10000 if d > 0x7FFF else d for d in deltas])
    sub += struct.pack(f">{seg_count}H", *([0] * seg_count))
    # fix subtable length now that it is assembled
    sub = sub[:2] + struct.pack(">H", 0) + struct.pack(">H", len(sub)) + sub[6:] \
        if False else struct.pack(">HHH", 4, len(sub), 0) + sub[6:]
    return struct.pack(">HHHHL", 0, 1, 3, 1, 12) + sub


def _name(family: str, style: str = "Regular") -> bytes:
    recs = [(1, family), (2, style), (3, f"{family} {style}"),
            (4, f"{family} {style}"),
            (6, family.replace(" ", "") + "-" + style.replace(" ", ""))]
    stored = b""
    entries = b""
    for nid, s in recs:
        enc = s.encode("utf-16-be")
        entries += struct.pack(">HHHHHH", 3, 1, 0x409, nid, len(enc),
                               len(stored))
        stored += enc
    return struct.pack(">HHH", 0, len(recs), 6 + 12 * len(recs)) \
        + entries + stored


def to_ttf(face: dict, family: str = "Zentropy Mint",
           style: str = "Regular") -> bytes:
    """A minted face document -> TrueType font bytes."""
    gsrc = face["glyphs"]
    order = [".notdef", "space"] + sorted(gsrc)
    cmap_map = {32: 1}
    for i, ch in enumerate(sorted(gsrc)):
        cmap_map[ord(ch)] = 2 + i

    glyf = b""
    loca = [0]
    hmtx = []
    gxmin = gymin = 32767
    gxmax = gymax = -32768
    max_pts = max_ctrs = 0
    for gname in order:
        if gname == ".notdef":
            hmtx.append((600, 0))
            loca.append(len(glyf))
            continue
        if gname == "space":
            hmtx.append((250, 0))
            loca.append(len(glyf))
            continue
        g = gsrc[gname]
        contours = []
        for ring in g["contours"]:
            pts = [(round(x), round(y)) for x, y in ring[:-1]]
            if len(pts) >= 3:
                contours.append(pts)
        entry, (x0, y0, x1, y1), npts, nctr = _glyf_entry(contours)
        glyf += _pad4(entry)
        loca.append(len(glyf))
        hmtx.append((round(g["advance"]), round(g["lsb"])))
        gxmin, gymin = min(gxmin, x0), min(gymin, y0)
        gxmax, gymax = max(gxmax, x1), max(gymax, y1)
        max_pts, max_ctrs = max(max_pts, npts), max(max_ctrs, nctr)

    n_glyphs = len(order)
    ascent = max(gymax + 60, 900)
    descent = min(gymin - 40, -180)

    head = struct.pack(">LLLLHHQQhhhhHHhhh",
                       0x00010000, 0x00010000, 0, 0x5F0F3CF5, 0b11, EM,
                       _EPOCH, _EPOCH, gxmin, gymin, gxmax, gymax,
                       0, 8, 2, 1, 0)
    hhea = struct.pack(">LhhhHhhhhhhhhhhhH",
                       0x00010000, ascent, descent, 0,
                       max(a for a, _ in hmtx),
                       min(l for _, l in hmtx),
                       0, gxmax, 1, 0, 0, 0, 0, 0, 0, 0, n_glyphs)
    maxp = struct.pack(">LHHHHHHHHHHHHHH",
                       0x00010000, n_glyphs, max_pts, max_ctrs, 0, 0, 2,
                       0, 0, 0, 0, 0, 0, 0, 0)
    hmtx_b = b"".join(struct.pack(">Hh", a, l) for a, l in hmtx)
    loca_b = struct.pack(f">{len(loca)}L", *loca)
    cmap_b = _cmap(cmap_map)
    name_b = _name(family, style)
    post = struct.pack(">LLhhLLLLLL", 0x00030000, 0, -75, 50, 0, 0, 0, 0,
                       0, 0)
    xh = int(face.get("metrics", {}).get("x_height", 500))
    weight = face.get("receipt", {}).get("params", {}).get("weight", 0.085)
    os2 = struct.pack(">HhHHHhhhhhhhhhhhh", 4,
                      sum(a for a, _ in hmtx) // n_glyphs,
                      max(100, min(900, round(weight * 4706))), 5, 0,
                      650, 600, 0, 0, 650, 600, 0, 0, 75, 50, 0, 0)
    os2 += b"\0" * 10                                # panose
    os2 += struct.pack(">LLLL", 1, 0, 0, 0)          # unicode ranges
    os2 += b"ZLAB"
    os2 += struct.pack(">HHHhhhHH", 0x40, 32, 115, ascent, descent, 0,
                       ascent, -descent)
    os2 += struct.pack(">LLhhHHH", 1, 0, xh, 0, 0, 32, 1)

    tables = {b"cmap": cmap_b, b"glyf": glyf, b"head": head,
              b"hhea": hhea, b"hmtx": hmtx_b, b"loca": loca_b,
              b"maxp": maxp, b"name": name_b, b"post": post,
              b"OS/2": os2}
    kern_src = face.get("kerning") or {}
    gid = {ch: 2 + i for i, ch in enumerate(sorted(gsrc))}
    pairs = sorted((gid[p[0]], gid[p[1]], int(v))
                   for p, v in kern_src.items()
                   if p[0] in gid and p[1] in gid and int(v) != 0)
    if pairs:
        import math as _m
        np_ = len(pairs)
        p2k = 2 ** int(_m.log2(np_)) if np_ else 1
        sub = struct.pack(">HHHHHHH", 0, 14 + 6 * np_, 0x0001, np_,
                          p2k * 6, int(_m.log2(p2k)), (np_ - p2k) * 6)
        for l, r, v in pairs:
            sub += struct.pack(">HHh", l, r, v)
        tables[b"kern"] = struct.pack(">HH", 0, 1) + sub
    tags = sorted(tables)
    n = len(tags)
    import math
    p2 = 2 ** int(math.log2(n))
    header = struct.pack(">LHHHH", 0x00010000, n, p2 * 16,
                         int(math.log2(p2)), (n - p2) * 16)
    offset = 12 + 16 * n
    dir_b = b""
    body = b""
    offsets = {}
    for tag in tags:
        data = tables[tag]
        offsets[tag] = offset
        dir_b += struct.pack(">4sLLL", tag, _checksum(data), offset,
                             len(data))
        body += _pad4(data)
        offset += len(_pad4(data))
    font = header + dir_b + body
    adjust = (0xB1B0AFBA - _checksum(font)) & 0xFFFFFFFF
    hoff = offsets[b"head"] + 8
    return font[:hoff] + struct.pack(">L", adjust) + font[hoff + 4:]
