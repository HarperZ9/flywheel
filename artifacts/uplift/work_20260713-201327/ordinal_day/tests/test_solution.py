import pytest
from solution import ordinal_day as f
def test_first(): assert f(2021, 1, 1) == 1
def test_last_common(): assert f(2021, 12, 31) == 365
def test_last_leap(): assert f(2020, 12, 31) == 366
def test_leap_march(): assert f(2020, 3, 1) == 61
def test_common_march(): assert f(2021, 3, 1) == 60
def test_feb_end(): assert f(2021, 2, 28) == 59
def test_bad_day_leap():
    with pytest.raises(ValueError) as e: f(2021, 2, 29)
    assert str(e.value) == 'bad day'
def test_bad_day_zero():
    with pytest.raises(ValueError): f(2021, 1, 0)
def test_bad_month():
    with pytest.raises(ValueError) as e: f(2021, 13, 1)
    assert str(e.value) == 'bad month'
def test_bad_year():
    with pytest.raises(ValueError) as e: f(0, 1, 1)
    assert str(e.value) == 'bad year'
