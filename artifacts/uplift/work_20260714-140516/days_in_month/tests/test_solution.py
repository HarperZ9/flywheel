import pytest
from solution import days_in_month as f
def test_leap_feb(): assert f(2020, 2) == 29
def test_century_common(): assert f(1900, 2) == 28
def test_century_leap(): assert f(2000, 2) == 29
def test_common_feb(): assert f(2021, 2) == 28
def test_april(): assert f(2021, 4) == 30
def test_january(): assert f(2021, 1) == 31
def test_december(): assert f(2021, 12) == 31
def test_bad_month_zero():
    with pytest.raises(ValueError) as e: f(2021, 0)
    assert str(e.value) == 'bad month'
def test_bad_month_high():
    with pytest.raises(ValueError): f(2021, 13)
def test_bad_year():
    with pytest.raises(ValueError) as e: f(0, 1)
    assert str(e.value) == 'bad year'
def test_bool_year():
    with pytest.raises(ValueError): f(True, 1)
