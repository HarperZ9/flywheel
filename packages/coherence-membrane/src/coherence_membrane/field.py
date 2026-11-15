"""Field -- the L0 scalar-field primitive (see spec sensory-transform-algebra)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FieldKind(str, Enum):
    LUMINANCE = "luminance"               # values in [0, 1]
    OCCUPANCY = "occupancy"               # values in {0.0, 1.0}
    SIGNED_DISTANCE = "signed-distance"   # values in R, 0 = surface


@dataclass(frozen=True)
class Field:
    """A 2-D scalar field with a first-class UNVERIFIABLE mask.

    values  -- row-major, length width*height.
    unknown -- row-major bool mask, True where the cell is UNVERIFIABLE.
    """

    width: int
    height: int
    kind: FieldKind
    values: tuple[float, ...]
    unknown: tuple[bool, ...]

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("field dimensions must be positive")
        n = self.width * self.height
        if len(self.values) != n:
            raise ValueError(f"values length {len(self.values)} != {n}")
        if len(self.unknown) != n:
            raise ValueError(f"unknown length {len(self.unknown)} != {n}")

    def index(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(f"({x},{y}) out of {self.width}x{self.height}")
        return y * self.width + x

    def at(self, x: int, y: int) -> float:
        return self.values[self.index(x, y)]

    def is_unknown(self, x: int, y: int) -> bool:
        return self.unknown[self.index(x, y)]
