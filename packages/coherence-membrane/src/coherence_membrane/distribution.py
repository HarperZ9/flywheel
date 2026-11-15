"""Distribution -- a discrete probability mass function as a checkable value.

The uncertainty arm of tier-2. Moments are re-derived from the raw mass (never a
stored field a caller could misstate); the distribution oracle checks claimed
moments against this re-derivation. v1 is discrete-pmf only; continuous/parametric
is a noted future extension. Moment methods assume total() > 0 (the oracle guards)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Distribution:
    """A discrete pmf as ordered (outcome, probability) pairs."""

    pairs: tuple[tuple[float, float], ...]

    def total(self) -> float:
        return sum(p for _, p in self.pairs)

    def mean(self) -> float:
        return sum(x * p for x, p in self.pairs) / self.total()

    def variance(self) -> float:
        mu = self.mean()
        return sum(p * (x - mu) ** 2 for x, p in self.pairs) / self.total()

    def support(self) -> tuple[float, ...]:
        return tuple(x for x, _ in self.pairs)
