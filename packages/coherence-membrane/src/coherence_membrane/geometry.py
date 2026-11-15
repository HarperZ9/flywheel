"""Geometry -- the L0 vector primitive (points / polylines / polygons).

The second L0 IR primitive alongside Field. Coordinates are floats in the source
field's pixel space (x rightward, y downward, matching Field row-major indexing).
UNVERIFIABLE is first-class: a Geometry carries the coordinates (cell centres)
where vector structure could not be determined (e.g. a contour cell with an
unknown corner), so downstream encoders report incompleteness rather than imply a
clean trace.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Polyline:
    """An ordered chain of points. `closed` => the last point connects back to the
    first (a polygon); the first point is NOT repeated at the end."""

    points: tuple[Point, ...]
    closed: bool = False

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("a polyline needs at least 2 points")
        if self.closed and len(self.points) < 3:
            raise ValueError("a closed polyline (polygon) needs at least 3 points")

    def __len__(self) -> int:
        return len(self.points)


@dataclass(frozen=True)
class Geometry:
    """A bundle of vector features in one coordinate space.

    paths   -- polylines / polygons (open or closed chains).
    points  -- isolated points (a point set), not part of any path.
    unknown -- coordinates where vector structure is UNVERIFIABLE (carried, never
              silently dropped).
    """

    paths: tuple[Polyline, ...] = ()
    points: tuple[Point, ...] = ()
    unknown: tuple[Point, ...] = ()

    def is_empty(self) -> bool:
        """True only when there is no content at all -- no paths, points, OR
        unknown markers. UNVERIFIABLE markers are first-class content (geometry
        with only unknowns is not 'empty'), consistent with to_coords."""
        return not self.paths and not self.points and not self.unknown

    def bbox(self) -> tuple[float, float, float, float] | None:
        pts = [p for pl in self.paths for p in pl.points] + list(self.points)
        if not pts:
            return None
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))
