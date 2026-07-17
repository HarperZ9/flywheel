import pytest
from solution import div_round_half_away


def test_basic_rounding():
    assert div_round_half_away(1, 3) == 0
    assert div_round_half_away(2, 3) == 1
    assert div_round_half_away(5, 4) == 1
    assert div_round_half_away(7, 4) == 2


def test_ties_away_from_zero_positive():
    assert div_round_half_away(7, 2) == 4
    assert div_round_half_away(1, 2) == 1
    assert div_round_half_away(3, 2) == 2
    assert div_round_half_away(5, 2) == 3


def test_ties_away_from_zero_negative():
    assert div_round_half_away(-7, 2) == -4
    assert div_round_half_away(7, -2) == -4
    assert div_round_half_away(-7, -2) == 4
    assert div_round_half_away(-1, 2) == -1


def test_zero_numerator():
    assert div_round_half_away(0, 5) == 0
    assert div_round_half_away(0, -5) == 0


def test_exact_division():
    assert div_round_half_away(10, 5) == 2
    assert div_round_half_away(-10, 5) == -2
    assert div_round_half_away(10, -5) == -2


def test_big_int_exactness():
    # (10**30 + 1) / 2 is an exact tie at 5*10**29 + 0.5 -> away from zero
    assert div_round_half_away(10**30 + 1, 2) == 5 * 10**29 + 1
    assert div_round_half_away(-(10**30 + 1), 2) == -(5 * 10**29 + 1)
    # 10**30 = 3*q + 1, remainder 1/3 < 1/2 -> rounds down
    assert div_round_half_away(10**30, 3) == (10**30 - 1) // 3
    # 10**30 + 2 is exactly divisible by 3 -> no rounding
    assert div_round_half_away(10**30 + 2, 3) == (10**30 + 2) // 3
    # 10**30 + 10 has remainder 2 -> 2/3 > 1/2 -> rounds up; float would lose precision
    assert div_round_half_away(10**30 + 10, 3) == (10**30 + 10) // 3 + 1


def test_zero_denominator_raises():
    with pytest.raises(ValueError):
        div_round_half_away(5, 0)


def test_bool_and_non_int_raise():
    with pytest.raises(ValueError):
        div_round_half_away(True, 2)
    with pytest.raises(ValueError):
        div_round_half_away(5, False)
    with pytest.raises(ValueError):
        div_round_half_away(1.5, 2)
    with pytest.raises(ValueError):
        div_round_half_away("4", 2)
