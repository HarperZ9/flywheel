from __future__ import annotations

import pytest

from coherence_membrane.certificate import Verdict
from coherence_membrane.quantity import (
    DIMENSIONLESS, LENGTH, MASS, TIME, Quantity, metre, newton,
)
from coherence_membrane.quantity_oracle import (
    QuantityClaim, check_consistent, check_dimensionless, check_equation,
    check_same_dimension,
)


def test_check_equation_f_equals_ma_verified():
    m = Quantity(2.0, MASS)
    a = Quantity(3.0, LENGTH / TIME ** 2)
    c = check_equation(m * a, 6.0 * newton)
    assert c.verdict is Verdict.VERIFIED
    assert c.oracle == "dimensional-invariant-v1"


def test_check_equation_pathological_tol_is_unverifiable():
    # an infinite/nan/negative rel_tol must NOT launder a false VERIFIED (soundness)
    a, b = Quantity(1.0, MASS), Quantity(999.0, MASS)
    assert check_equation(a, b, rel_tol=float("inf")).verdict is Verdict.UNVERIFIABLE
    assert check_equation(a, b, rel_tol=float("nan")).verdict is Verdict.UNVERIFIABLE
    assert check_equation(a, b, rel_tol=-1.0).verdict is Verdict.UNVERIFIABLE


def test_check_equation_wrong_magnitude_refuted():
    m = Quantity(2.0, MASS)
    a = Quantity(3.0, LENGTH / TIME ** 2)
    c = check_equation(m * a, 7.0 * newton)
    assert c.verdict is Verdict.REFUTED
    assert dict(c.evidence)["lhs"] == repr(6.0)


def test_check_equation_dimension_mismatch_refuted():
    c = check_equation(Quantity(1.0, MASS), Quantity(1.0, LENGTH))
    assert c.verdict is Verdict.REFUTED
    assert "lhs_dim" in dict(c.evidence)


def test_check_equation_non_finite_unverifiable():
    c = check_equation(Quantity(float("nan"), MASS), Quantity(1.0, MASS))
    assert c.verdict is Verdict.UNVERIFIABLE


def test_check_same_dimension_and_dimensionless():
    assert check_same_dimension(Quantity(1.0, MASS), Quantity(9.0, MASS)).verdict is Verdict.VERIFIED
    assert check_same_dimension(Quantity(1.0, MASS), Quantity(1.0, LENGTH)).verdict is Verdict.REFUTED
    assert check_dimensionless(Quantity(0.5, DIMENSIONLESS)).verdict is Verdict.VERIFIED
    assert check_dimensionless(metre).verdict is Verdict.REFUTED


def test_check_consistent_catches_dimension_error():
    m = Quantity(2.0, MASS)
    a = Quantity(3.0, LENGTH / TIME ** 2)
    assert check_consistent(lambda: m * a).verdict is Verdict.VERIFIED
    assert check_consistent(lambda: m + a).verdict is Verdict.REFUTED     # DimensionError
    assert check_consistent(lambda: 1 / 0).verdict is Verdict.UNVERIFIABLE  # not our invariant


def test_quantity_claim_is_frozen():
    claim = QuantityClaim("x", Quantity(1.0, MASS), Quantity(1.0, MASS))
    assert claim.rel_tol == 1e-9
    with pytest.raises(AttributeError):
        claim.lhs = Quantity(2.0, MASS)
