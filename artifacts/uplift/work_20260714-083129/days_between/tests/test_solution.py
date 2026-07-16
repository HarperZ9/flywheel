import pytest
from solution import days_between as f
def test_same(): assert f((1970, 1, 1), (1970, 1, 1)) == 0
def test_next(): assert f((1970, 1, 1), (1970, 1, 2)) == 1
def test_prev(): assert f((1970, 1, 2), (1970, 1, 1)) == -1
def test_leap_cross(): assert f((2020, 2, 28), (2020, 3, 1)) == 2
def test_common_cross(): assert f((2019, 2, 28), (2019, 3, 1)) == 1
def test_leap_year_span(): assert f((2000, 1, 1), (2001, 1, 1)) == 366
def test_bad_date():
    with pytest.raises(ValueError) as e: f((2021, 2, 29), (2021, 3, 1))
    assert str(e.value) == 'bad date'
def test_not_tuple():
    with pytest.raises(ValueError): f([1970, 1, 1], (1970, 1, 2))
def test_bool():
    with pytest.raises(ValueError): f((1970, 1, 1), (1970, 1, True))
