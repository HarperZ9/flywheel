import pytest
from solution import canonical_decimal


def test_integers():
    assert canonical_decimal("42") == "42"
    assert canonical_decimal("007") == "7"
    assert canonical_decimal("0") == "0"


def test_fractions():
    assert canonical_decimal("3.1400") == "3.14"
    assert canonical_decimal("5.") == "5"
    assert canonical_decimal(".5") == "0.5"
    assert canonical_decimal("0.50") == "0.5"
    assert canonical_decimal("2.000") == "2"


def test_zero_normalization():
    assert canonical_decimal("-0") == "0"
    assert canonical_decimal("-0.000") == "0"
    assert canonical_decimal("+0.0") == "0"
    assert canonical_decimal("-00.0") == "0"
    assert canonical_decimal("-.0") == "0"


def test_signs():
    assert canonical_decimal("+12") == "12"
    assert canonical_decimal("-12.30") == "-12.3"
    assert canonical_decimal("-.5") == "-0.5"
    assert canonical_decimal("+0.10") == "0.1"


def test_underscores():
    assert canonical_decimal("1_000") == "1000"
    assert canonical_decimal("+001_0.25_00") == "10.25"
    assert canonical_decimal("1_2.3_4") == "12.34"


def test_bad_underscores_raise():
    for bad in ["_1", "1_", "1__2", "1_.5", "1._5", "+_1", "1.5_"]:
        with pytest.raises(ValueError):
            canonical_decimal(bad)


def test_no_digits_raise():
    for bad in ["", "+", "-", ".", "+.", "-."]:
        with pytest.raises(ValueError):
            canonical_decimal(bad)


def test_bad_chars_raise():
    for bad in ["1a", " 1", "1 ", "1.2.3", "--1", "+-1", "1,000", "1e5"]:
        with pytest.raises(ValueError):
            canonical_decimal(bad)
