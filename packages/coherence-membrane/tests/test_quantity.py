from __future__ import annotations

from fractions import Fraction

import pytest

from coherence_membrane.quantity import (
    CURRENT, DIMENSIONLESS, LENGTH, MASS, TIME, Dimension, DimensionError, Quantity,
    coulomb, hertz, joule, kilogram, metre, newton, ohm, pascal, second, volt, watt,
)


def test_dimension_algebra_exact():
    accel = LENGTH / TIME ** 2
    assert accel == Dimension((1, 0, -2, 0, 0, 0, 0))
    assert (MASS * accel) == newton.dim
    assert DIMENSIONLESS.is_dimensionless
    assert not LENGTH.is_dimensionless


def test_dimension_fractional_exponent_is_exact():
    half = TIME ** Fraction(1, 2)
    assert half.exponents[2] == Fraction(1, 2)
    assert (half * half) == TIME            # 1/2 + 1/2 == 1 exactly, not 0.9999…


def test_quantity_add_requires_same_dimension():
    assert (Quantity(1.0, LENGTH) + Quantity(2.0, LENGTH)).magnitude == 3.0
    with pytest.raises(DimensionError):
        Quantity(1.0, LENGTH) + Quantity(1.0, TIME)


def test_quantity_sub_requires_same_dimension():
    assert (Quantity(3.0, LENGTH) - Quantity(1.0, LENGTH)).magnitude == 2.0
    with pytest.raises(DimensionError):
        Quantity(1.0, LENGTH) - Quantity(1.0, TIME)


def test_quantity_mul_div_compose_dimension():
    m = Quantity(2.0, MASS)
    a = Quantity(3.0, LENGTH / TIME ** 2)
    f = m * a
    assert f.magnitude == 6.0
    assert f.dim == newton.dim
    assert (3.0 * metre).magnitude == 3.0       # scalar * quantity (__rmul__)
    assert hertz.dim == (DIMENSIONLESS / TIME)  # hertz == 1 / second (__rtruediv__)


def test_derived_units_have_correct_dimensions():
    assert newton.dim == MASS * LENGTH / TIME ** 2
    assert joule.dim == newton.dim * LENGTH
    assert watt.dim == joule.dim / TIME
    assert newton.magnitude == 1.0
    assert (1 / second).dim == hertz.dim


def test_multi_op_derived_units_have_correct_dimensions():
    # volt/ohm derive through several composed ops -- lock their dimensions explicitly
    assert pascal.dim == MASS / (LENGTH * TIME ** 2)                # Pa = kg·m^-1·s^-2
    assert coulomb.dim == CURRENT * TIME                            # C = A·s
    assert volt.dim == MASS * LENGTH ** 2 / (TIME ** 3 * CURRENT)   # V = kg·m^2·s^-3·A^-1
    assert ohm.dim == volt.dim / CURRENT                           # ohm = V/A
