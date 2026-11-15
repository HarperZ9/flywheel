"""phyllotaxis -- the golden-angle structural measure (the first structural_fitness ideal).

A point arrangement grown by adding each element at a fixed +137.5078 deg turn (the
golden angle, 360*(1 - 1/phi)) with steadily increasing radius is the phyllotactic
spiral of sunflowers, pinecones, and succulents -- nature's densest, most-even packing.
This measures how close a point sequence is to that signature: take the points IN
GENERATION ORDER, find their centroid (a translation-invariant angular origin), and
average the circular distance between each consecutive divergence angle and the golden
angle (direction-agnostic -- a clockwise spiral's ~= 360 - golden is accepted equally).
0 = a perfect golden spiral; large = unstructured or a different angle. Fewer than
MIN_SPIRAL_POINTS usable points -> infinity, which structural_fitness reads as
UNVERIFIABLE: the deviation is a MEAN over consecutive gaps, and too few gaps cannot
discriminate a spiral from a coincidence, so "can't tell" is the honest verdict (not a
shaky fit). Pure math; perceive a work's generated points with an organ, judge here.

NOTE the contract: `points` must be in GENERATION ORDER (the order elements were placed).
Recovering order by radius-sorting about an estimated center is fatally fragile -- a
centroid a hair off the true center reorders near-center points and destroys the signal;
the per-step angular increment is the sound invariant."""
from __future__ import annotations

import math

PHI = (1.0 + math.sqrt(5.0)) / 2.0
GOLDEN_ANGLE = 360.0 * (1.0 - 1.0 / PHI)   # 137.50776405003788 degrees
# Below this many usable points the mean over consecutive divergence gaps (= points - 1
# gaps) carries too little signal to tell a golden spiral from a coincidental low score,
# so the measure returns inf -> UNVERIFIABLE rather than risk a false "fit". A real
# phyllotactic arrangement is dense (hundreds of points); this floor only fences the
# statistically-meaningless tail.
MIN_SPIRAL_POINTS = 8


def _circular_distance(a: float, b: float) -> float:
    """Shortest distance (degrees) between two angles on the circle [0, 360)."""
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def golden_angle_deviation(points) -> float:
    """Mean circular distance of the generation-order consecutive divergence angles from
    the golden angle (direction-agnostic). `points` is an iterable of (x, y) pairs IN
    GENERATION ORDER. Returns inf when fewer than MIN_SPIRAL_POINTS points have a defined
    angle about the centroid (too few gaps to discriminate a spiral) -- structural_fitness
    maps inf to UNVERIFIABLE."""
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < MIN_SPIRAL_POINTS:
        return math.inf
    cx = sum(x for x, _ in pts) / len(pts)
    cy = sum(y for _, y in pts) / len(pts)
    angles = []
    for x, y in pts:
        dx, dy = x - cx, y - cy
        if math.hypot(dx, dy) > 0.0:
            angles.append(math.degrees(math.atan2(dy, dx)) % 360.0)
    if len(angles) < MIN_SPIRAL_POINTS:
        return math.inf
    g, gc = GOLDEN_ANGLE, 360.0 - GOLDEN_ANGLE
    gaps = []
    for a0, a1 in zip(angles, angles[1:]):
        dtheta = (a1 - a0) % 360.0
        gaps.append(min(_circular_distance(dtheta, g), _circular_distance(dtheta, gc)))
    return sum(gaps) / len(gaps)
