"""Quantity + Dimension -- value-with-units as a checkable primitive.

The dimensional arm of the verifier layer's tier-2 (invariant) oracle. A Quantity
carries an exact Dimension (7 SI base exponents as Fractions); arithmetic enforces
dimensional homogeneity -- you cannot add metres to seconds. This makes the single
highest-leverage error class (units confusion) a structural impossibility, and the
ground the dimensional oracle re-derives its verdicts from.

Integer/Fraction exponents are exact; a float exponent may be imprecise -- pass a
Fraction for exact fractional powers (e.g. dim ** Fraction(1, 2))."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

_BASE_SYMBOLS = ("L", "M", "T", "I", "Θ", "N", "J")  # 7 SI base dimensions


class DimensionError(ValueError):
    """A dimensionally-invalid operation (e.g. metre + second). The
    structural-violation signal the dimensional oracle maps to REFUTED."""


@dataclass(frozen=True)
class Dimension:
    """Exact dimension: Fraction exponents over (length, mass, time, current,
    temperature, amount, luminous intensity)."""

    exponents: tuple[Fraction, ...]

    def __post_init__(self) -> None:
        if len(self.exponents) != 7:
            raise ValueError("Dimension needs exactly 7 exponents")
        object.__setattr__(self, "exponents", tuple(Fraction(e) for e in self.exponents))

    def __mul__(self, other: "Dimension") -> "Dimension":
        return Dimension(tuple(a + b for a, b in zip(self.exponents, other.exponents)))

    def __truediv__(self, other: "Dimension") -> "Dimension":
        return Dimension(tuple(a - b for a, b in zip(self.exponents, other.exponents)))

    def __pow__(self, k) -> "Dimension":
        f = Fraction(k)
        return Dimension(tuple(a * f for a in self.exponents))

    @property
    def is_dimensionless(self) -> bool:
        return all(e == 0 for e in self.exponents)

    def __str__(self) -> str:
        parts = [
            (s if e == 1 else f"{s}^{e}")
            for s, e in zip(_BASE_SYMBOLS, self.exponents)
            if e != 0
        ]
        return "·".join(parts) if parts else "1"


def _dim(L=0, M=0, T=0, I=0, K=0, N=0, J=0) -> Dimension:
    return Dimension((L, M, T, I, K, N, J))


DIMENSIONLESS = _dim()
LENGTH = _dim(L=1)
MASS = _dim(M=1)
TIME = _dim(T=1)
CURRENT = _dim(I=1)
TEMPERATURE = _dim(K=1)
AMOUNT = _dim(N=1)
LUMINOUS = _dim(J=1)


@dataclass(frozen=True)
class Quantity:
    """A magnitude (in SI base units) carrying an exact Dimension."""

    magnitude: float
    dim: Dimension

    def __add__(self, other: "Quantity") -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        if self.dim != other.dim:
            raise DimensionError(f"cannot add {self.dim} + {other.dim}")
        return Quantity(self.magnitude + other.magnitude, self.dim)

    def __sub__(self, other: "Quantity") -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        if self.dim != other.dim:
            raise DimensionError(f"cannot subtract {self.dim} - {other.dim}")
        return Quantity(self.magnitude - other.magnitude, self.dim)

    def __mul__(self, other) -> "Quantity":
        if isinstance(other, (int, float)):
            return Quantity(self.magnitude * other, self.dim)
        if isinstance(other, Quantity):
            return Quantity(self.magnitude * other.magnitude, self.dim * other.dim)
        return NotImplemented

    __rmul__ = __mul__

    def __truediv__(self, other) -> "Quantity":
        if isinstance(other, (int, float)):
            return Quantity(self.magnitude / other, self.dim)
        if isinstance(other, Quantity):
            return Quantity(self.magnitude / other.magnitude, self.dim / other.dim)
        return NotImplemented

    def __rtruediv__(self, other) -> "Quantity":
        if isinstance(other, (int, float)):
            return Quantity(other / self.magnitude, DIMENSIONLESS / self.dim)
        return NotImplemented

    def __pow__(self, k) -> "Quantity":
        return Quantity(self.magnitude ** k, self.dim ** k)

    def __neg__(self) -> "Quantity":
        return Quantity(-self.magnitude, self.dim)


metre = Quantity(1.0, LENGTH)
kilogram = Quantity(1.0, MASS)
second = Quantity(1.0, TIME)
ampere = Quantity(1.0, CURRENT)
kelvin = Quantity(1.0, TEMPERATURE)
mole = Quantity(1.0, AMOUNT)
candela = Quantity(1.0, LUMINOUS)

newton = kilogram * metre / second ** 2
joule = newton * metre
pascal = newton / metre ** 2
watt = joule / second
hertz = 1 / second
coulomb = ampere * second
volt = watt / ampere
ohm = volt / ampere
