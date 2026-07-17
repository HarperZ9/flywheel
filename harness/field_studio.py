"""field_studio.py: a real field, solved and drawn.

The Laplace equation on a seeded grid: boundary charges placed by the
same generator that lays out the aperture, relaxed to equilibrium, then
rendered the way an engineer annotates and an artist grains it: graph
paper, the field as shading, equipotentials as fine line-work, and a
measurement frame around the hottest region. The physics is honest: the
receipt carries the boundary spec, the iteration count, and the final
residual, so the solve itself is a measurement anyone can re-run.
"""
from __future__ import annotations

import hashlib
import json
import random

SCHEMA = "flywheel.field-study/v1"


def _solve(seed: int, gw: int, gh: int, n_sources: int, iters: int):
    """Jacobi relaxation of the Laplace equation with seeded Dirichlet
    boundary charges. Returns the field, the boundary spec, and the final
    residual (the physics receipt)."""
    rng = random.Random(seed)
    fixed = {}
    for _ in range(n_sources):
        x = rng.randrange(gw // 8, gw - gw // 8)
        y = rng.randrange(gh // 8, gh - gh // 8)
        fixed[(x, y)] = rng.choice([1.0, 1.0, -1.0])
    # cold frame: the grid's edge is grounded
    for x in range(gw):
        fixed[(x, 0)] = 0.0
        fixed[(x, gh - 1)] = 0.0
    for y in range(gh):
        fixed[(0, y)] = 0.0
        fixed[(gw - 1, y)] = 0.0

    f = [[0.0] * gw for _ in range(gh)]
    for (x, y), v in fixed.items():
        f[y][x] = v
    # Gauss-Seidel with over-relaxation: an order of magnitude fewer
    # sweeps than Jacobi to the same residual on a grid this size
    omega = 1.9
    residual = 1.0
    it = 0
    for it in range(1, iters + 1):
        residual = 0.0
        for y in range(1, gh - 1):
            fy, fy0, fy1 = f[y], f[y - 1], f[y + 1]
            for x in range(1, gw - 1):
                if (x, y) in fixed:
                    continue
                dv = 0.25 * (fy[x - 1] + fy[x + 1]
                             + fy0[x] + fy1[x]) - fy[x]
                if abs(dv) > residual:
                    residual = abs(dv)
                fy[x] += omega * dv
        if residual < 1e-4:
            break
    spec = sorted((x, y, v) for (x, y), v in fixed.items()
                  if 0 < x < gw - 1 and 0 < y < gh - 1)
    return f, spec, residual, it


def field_study(seed: int = 58, width: int = 640, height: int = 400,
                sources: int = 3, levels: int = 9, iters: int = 600):
    """Solve and draw; returns (PIL image, receipt) or (None, error)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None, {"error": "field studies need Pillow on the engine side"}
    width = max(64, min(1600, int(width)))
    height = max(64, min(1600, int(height)))
    sources = max(1, min(8, int(sources)))
    levels = max(3, min(24, int(levels)))
    gw, gh = 160, max(40, int(160 * height / width))

    field, spec, residual, it = _solve(int(seed), gw, gh, sources,
                                       max(50, min(2000, int(iters))))

    img = Image.new("RGB", (width, height), (11, 14, 15))
    d = ImageDraw.Draw(img)
    sx, sy = width / gw, height / gh

    # the field as quiet shading; magnitude carries the light
    px = img.load()
    for y in range(gh):
        for x in range(gw):
            v = field[y][x]
            if abs(v) < 0.004:
                continue
            shade = min(1.0, abs(v)) ** 0.6
            base = int(34 * shade)
            c = (11 + int(150 * shade), 14 + base // 2, 15 + base // 2) \
                if v > 0 else (11 + base // 2, 14 + base // 2,
                               15 + int(130 * shade))
            for yy in range(int(y * sy), min(height, int((y + 1) * sy) + 1)):
                for xx in range(int(x * sx),
                                min(width, int((x + 1) * sx) + 1)):
                    px[xx, yy] = c

    # graph paper over the shading
    grid_c = (30, 34, 35)
    for gx in range(0, width, max(8, width // 24)):
        d.line((gx, 0, gx, height), fill=grid_c, width=1)
    for gy in range(0, height, max(8, height // 15)):
        d.line((0, gy, width, gy), fill=grid_c, width=1)

    # equipotentials: fine ink where the field crosses each level
    ink = (238, 241, 238)
    lvls = [(-1.0 + 2.0 * (k + 1) / (levels + 1)) for k in range(levels)]
    for y in range(gh - 1):
        for x in range(gw - 1):
            a, b = field[y][x], field[y][x + 1]
            c2 = field[y + 1][x]
            for lv in lvls:
                if abs(lv) < 1e-9:
                    continue
                if (a - lv) * (b - lv) < 0 or (a - lv) * (c2 - lv) < 0:
                    d.point((int(x * sx), int(y * sy)), fill=ink)
                    break

    # the measurement frame: axes through the hottest cell, like a
    # dimension callout on a drawing
    hx, hy, hv = 0, 0, 0.0
    for (x, y, v) in spec:
        if abs(v) >= abs(hv):
            hx, hy, hv = x, y, v
    ax, ay = hx * sx, hy * sy
    hot = (255, 120, 130) if hv > 0 else (130, 160, 255)
    d.line((ax, ay, ax, max(8, ay - height * 0.30)), fill=hot, width=1)
    d.line((ax, ay, min(width - 8, ax + width * 0.24), ay), fill=hot, width=1)
    tip = max(8, ay - height * 0.30)
    d.polygon([(ax, tip), (ax - 3, tip + 7), (ax + 3, tip + 7)], fill=hot)
    rgt = min(width - 8, ax + width * 0.24)
    d.polygon([(rgt, ay), (rgt - 7, ay - 3), (rgt - 7, ay + 3)], fill=hot)

    boundary_sha = hashlib.sha256(
        json.dumps(spec, sort_keys=True).encode()).hexdigest()
    receipt = {"op": "field", "schema": SCHEMA, "seed": int(seed),
               "equation": "laplace", "grid": [gw, gh],
               "n_sources": sources, "levels": levels,
               "iterations": it, "residual": round(residual, 8),
               "converged": residual < 1e-4,
               "boundary_sha256": boundary_sha}
    return img, receipt
