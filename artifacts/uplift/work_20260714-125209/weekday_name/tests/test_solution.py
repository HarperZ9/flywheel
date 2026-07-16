import pytest
from solution import weekday_name as f
def test_millennium(): assert f(2000, 1, 1) == 'Saturday'
def test_2021(): assert f(2021, 1, 1) == 'Friday'
def test_epoch(): assert f(1970, 1, 1) == 'Thursday'
def test_leap_2024(): assert f(2024, 2, 29) == 'Thursday'
def test_leap_2016(): assert f(2016, 2, 29) == 'Monday'
def test_bad_day():
    with pytest.raises(ValueError) as e: f(2021, 2, 29)
    assert str(e.value) == 'bad day'
def test_bad_month():
    with pytest.raises(ValueError) as e: f(2021, 0, 1)
    assert str(e.value) == 'bad month'
def test_bad_year():
    with pytest.raises(ValueError) as e: f(0, 1, 1)
    assert str(e.value) == 'bad year'
