import pytest
from solution import add_months


def test_clamp_to_shorter_month():
    assert add_months(2023, 1, 31, 1) == (2023, 2, 28)
    assert add_months(2024, 1, 31, 1) == (2024, 2, 29)
    assert add_months(2023, 3, 31, 1) == (2023, 4, 30)


def test_leap_day_plus_year_clamps():
    assert add_months(2024, 2, 29, 12) == (2025, 2, 28)
    assert add_months(2024, 2, 29, 48) == (2028, 2, 29)


def test_negative_n_and_year_carry():
    assert add_months(2023, 12, 15, -13) == (2022, 11, 15)
    assert add_months(2024, 3, 31, -1) == (2024, 2, 29)
    assert add_months(2023, 1, 10, -1) == (2022, 12, 10)


def test_zero_n_identity():
    assert add_months(2021, 7, 4, 0) == (2021, 7, 4)


def test_century_leap_rules():
    assert add_months(1900, 1, 29, 1) == (1900, 2, 28)
    assert add_months(2000, 1, 29, 1) == (2000, 2, 29)
    assert add_months(2100, 1, 30, 1) == (2100, 2, 28)


def test_years_beyond_datetime_range():
    # year 1000000 is divisible by 400 -> leap; datetime caps at 9999
    assert add_months(999999, 12, 31, 2) == (1000000, 2, 29)
    # 99999 % 4 == 3 -> not leap
    assert add_months(99999, 1, 31, 1) == (99999, 2, 28)


def test_invalid_input_date_raises():
    with pytest.raises(ValueError):
        add_months(2023, 2, 29, 0)
    with pytest.raises(ValueError):
        add_months(2023, 13, 1, 0)
    with pytest.raises(ValueError):
        add_months(2023, 0, 5, 0)
    with pytest.raises(ValueError):
        add_months(2023, 4, 31, 0)
    with pytest.raises(ValueError):
        add_months(0, 1, 1, 0)


def test_result_year_below_one_raises():
    with pytest.raises(ValueError):
        add_months(1, 1, 15, -1)
    with pytest.raises(ValueError):
        add_months(1, 3, 10, -5)


def test_bool_and_non_int_raise():
    with pytest.raises(ValueError):
        add_months(True, 1, 1, 0)
    with pytest.raises(ValueError):
        add_months(2023, True, 1, 0)
    with pytest.raises(ValueError):
        add_months(2023, 1, 1, True)
    with pytest.raises(ValueError):
        add_months(2023.0, 1, 1, 0)
