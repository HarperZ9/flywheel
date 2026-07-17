"""retro_cgi.py: wireframes and horizon grids, the old-computer display
language, rendered deterministically.

Flywheel's implementation of the retro-CGI domain the telos creative
engine declares (wireframes, horizon grids, measurement-friendly depth):
a tiny perspective projector over seeded primitives, drawn as fine
line-work with scanlines, every frame re-derivable from seed + params
and the geometry hashed onto the receipt.
"""
from __future__ import annotations

import hashlib
import json
import math
import random

GROUNDS = {"dark": (11, 14, 15), "ceramic": (244, 243, 239)}
INKS = {"dark": (238, 241, 238), "ceramic": (11, 12, 14)}

PRIMITIVES = ("cube", "pyramid", "orbit-sphere", "horizon")


def _cube():
    v = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    e = [(a, b) for a in range(8) for b in range(a + 1, 8)
         if sum(1 for i in range(3) if v[a][i] != v[b][i]) == 1]
    return v, e

def _pyramid():
    v = [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1), (0, 1.2, 0)]
    e = [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4)]
    return v, e

def _orbit_sphere(rings=7, segs=18):
    v, e = [], []
    for r in range(1, rings + 1):
        phi = math.pi * r / (rings + 1)
        ring = []
        for s in range(segs):
            th = 2 * math.pi * s / segs
            ring.append(len(v))
            v.append((math.sin(phi) * math.cos(th), math.cos(phi),
                      math.sin(phi) * math.sin(th)))
        for i in range(segs):
            e.append((ring[i], ring[(i + 1) % segs]))
    return v, e

def _horizon(lines=11, span=6.0):
    v, e = [], []
    for i in range(lines):
        x = -span / 2 + span * i / (lines - 1)
        v += [(x, -1.0, 0.4), (x, -1.0, span)]
        e.append((len(v) - 2, len(v) - 1))
    for i in range(lines):
        z = 0.4 + (span - 0.4) * (i / (lines - 1)) ** 1.6
        v += [(-span / 2, -1.0, z), (span / 2, -1.0, z)]
        e.append((len(v) - 2, len(v) - 1))
    return v, e

_BUILDERS = {"cube": _cube, "pyramid": _pyramid,
             "orbit-sphere": _orbit_sphere, "horizon": _horizon}


def _rotate(p, rx, ry):
    x, y, z = p
    y, z = (y * math.cos(rx) - z * math.sin(rx),
            y * math.sin(rx) + z * math.cos(rx))
    x, z = (x * math.cos(ry) + z * math.sin(ry),
            -x * math.sin(ry) + z * math.cos(ry))
    return x, y, z


def render_wireframe(primitive: str = "cube", seed: int = 58,
                     width: int = 480, height: int = 300,
                     ground: str = "dark", scanlines: bool = True):
    """Seed + primitive -> a PIL image and the geometry receipt."""
    from PIL import Image, ImageDraw
    if primitive not in _BUILDERS:
        return None, {"error": f"unknown primitive {primitive!r}; have: "
                               + ", ".join(sorted(_BUILDERS))}
    if ground not in GROUNDS:
        return None, {"error": f"unknown ground {ground!r}"}
    width = max(64, min(1600, int(width)))
    height = max(64, min(1600, int(height)))
    rng = random.Random(int(seed))
    rx, ry = rng.uniform(0.15, 0.6), rng.uniform(0.2, 2 * math.pi)
    verts, edges = _BUILDERS[primitive]()
    cam_z, f = 4.2, 2.6
    if primitive == "horizon":
        rx, ry, cam_z = 0.0, 0.0, 0.0

    img = Image.new("RGB", (width, height), GROUNDS[ground])
    draw = ImageDraw.Draw(img)
    ink = INKS[ground]
    s = min(width, height) * 0.36
    pts, zs = [], []
    for p in verts:
        x, y, z = _rotate(p, rx, ry) if primitive != "horizon" else p
        z += cam_z
        zs.append(z)
        px = width / 2 + (x * f / z) * s
        py = height / 2 - (y * f / z) * s
        pts.append((px, py))
    for a, b in edges:
        # depth cues the line weight: nearer edges press harder
        near = min(zs[a], zs[b])
        shade = tuple(int(g + (i - g) * min(1.0, 2.2 / near))
                      for g, i in zip(GROUNDS[ground], ink))
        draw.line((pts[a], pts[b]), fill=shade, width=1)
    if scanlines:
        dark = tuple(max(0, c - 12) for c in GROUNDS[ground])
        for y in range(0, height, 4):
            draw.line((0, y, width, y), fill=dark, width=1)

    geometry_sha = hashlib.sha256(json.dumps(
        {"verts": [[round(c, 6) for c in v] for v in verts],
         "edges": edges, "rx": round(rx, 6), "ry": round(ry, 6)},
        sort_keys=True).encode()).hexdigest()
    receipt = {"op": "wireframe", "primitive": primitive, "seed": int(seed),
               "n_vertices": len(verts), "n_edges": len(edges),
               "depth_range": [round(min(zs), 3), round(max(zs), 3)],
               "geometry_sha256": geometry_sha}
    return img, receipt
