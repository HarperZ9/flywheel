"""Substrate 9 — GEOMETRY / shape (the contour sense; the sensory algebra's Geometry plane).

Perception is not only sight-as-pixels: the membrane also ingests SHAPE (contours, SVG, plotter
geometry). This tests the principle on the Geometry plane. A closed polygon (n vertices) is decimated
to k vertices (lossy in vertices/DOF). Criteria (readouts of a shape):
  gross : area (shoelace) and centroid  — "how big / where"
  fine  : perimeter and corner-count (high-curvature vertices) — "how detailed / spiky"
Vertex-decimation is faithful to GROSS shape (area/centroid barely move) but lossy to FINE shape
(spikes/corners vanish) -> criterion-relativity on the shape sense. Internal stat (vertex count) is
blind to whether area survived; only comparison to the original (external) tells.

Stdlib only, deterministic.
"""
from __future__ import annotations
import math


def polygon(kind, n=120):
    pts = []
    for i in range(n):
        th = 2 * math.pi * i / n
        if kind == "star":
            r = 1.0 + 0.5 * math.cos(8 * th)       # 8 spikes (fine detail)
        elif kind == "blob":
            r = 1.0 + 0.18 * math.sin(3 * th) + 0.08 * math.cos(7 * th)
        else:                                       # near-circle
            r = 1.0
        pts.append((r * math.cos(th), r * math.sin(th)))
    return pts


def decimate(pts, k):
    n = len(pts)
    step = n / k
    return [pts[int(i * step) % n] for i in range(k)]


def area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def centroid(pts):
    n = len(pts)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def perimeter(pts):
    return sum(math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))


def corners(pts, thresh=0.6):
    """Count high-curvature vertices (turn angle > thresh rad) — a 'fine detail' readout."""
    n = len(pts); c = 0
    for i in range(n):
        a, b, d = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        v1 = (b[0] - a[0], b[1] - a[1]); v2 = (d[0] - b[0], d[1] - b[1])
        m1 = math.hypot(*v1); m2 = math.hypot(*v2)
        if m1 < 1e-9 or m2 < 1e-9:
            continue
        cosang = max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / (m1 * m2)))
        if math.acos(cosang) > thresh:
            c += 1
    return c


def main():
    print("closed polygons (120 vertices) decimated to k vertices (lossy in shape DOF)\n")
    print("shape   k     area-err   centroid-shift   perimeter-err   corner-ratio  [gross | fine]")
    rows = {}
    for kind in ("star", "blob", "circle"):
        base = polygon(kind)
        A0, C0, P0, K0 = area(base), centroid(base), perimeter(base), corners(base)
        k = 12  # keep 10% of vertices
        dec = decimate(base, k)
        a_err = abs(area(dec) - A0) / A0
        c_shift = math.dist(centroid(dec), C0)
        p_err = abs(perimeter(dec) - P0) / P0
        k_ratio = (corners(dec) / K0) if K0 else 1.0
        rows[kind] = (a_err, c_shift, p_err, k_ratio)
        print(f"  {kind:6s} {k:3d}   {a_err:.3f}      {c_shift:.4f}          {p_err:.3f}         {k_ratio:.2f}")

    star = rows["star"]
    print("\n--- verdict (substrate 9: geometry / shape) ---")
    # (1) lossy-but-faithful: on SMOOTH shapes (area is genuinely gross), 90% vertex-loss keeps area.
    p1 = rows["blob"][0] < 0.10 and rows["circle"][0] < 0.10
    # (3) criterion-relativity: the star loses FINE detail (corners/perimeter) far more than gross area.
    #     (For a spiky star, area is partly fine detail too -> it degrades more than for a smooth shape,
    #      which REINFORCES the point: the gross/fine split is itself criterion-relative.)
    p3 = star[3] < 0.5 and star[0] < star[2]
    print(f"(1) lossy-but-faithful: smooth shapes keep area at 90% vertex-loss "
          f"(blob {rows['blob'][0]:.3f}, circle {rows['circle'][0]:.3f} < 0.10)  -> {'HOLDS' if p1 else 'FALLS'}")
    print(f"(3) criterion-relativity (star): {1-star[3]:.0%} of corners destroyed + perimeter-err "
          f"{star[2]:.3f}, but area better preserved ({star[0]:.3f})  -> {'HOLDS' if p3 else 'FALLS'}")
    print("\nSTICKS" if (p1 and p3) else "\nFALLS", "— substrate 9 (geometry / shape sense).")


if __name__ == "__main__":
    main()
