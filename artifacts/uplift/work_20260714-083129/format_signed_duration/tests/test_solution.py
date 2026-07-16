import pytest
from solution import format_duration


def test_zero():
    assert format_duration(0) == "0:00"


def test_minutes_form_below_threshold():
    assert format_duration(59) == "0:59"
    assert format_duration(60) == "1:00"
    assert format_duration(61) == "1:01"
    assert format_duration(3599) == "59:59"


def test_threshold_exactly_3600_uses_hours_form():
    assert format_duration(3600) == "1:00:00"
    assert format_duration(3601) == "1:00:01"
    assert format_duration(3660) == "1:01:00"


def test_negative_values():
    assert format_duration(-59) == "-0:59"
    assert format_duration(-61) == "-1:01"
    assert format_duration(-3600) == "-1:00:00"
    assert format_duration(-3599) == "-59:59"


def test_large_hours_unpadded():
    assert format_duration(360000) == "100:00:00"
    assert format_duration(86461) == "24:01:01"
    assert format_duration(-360000) == "-100:00:00"


def test_component_padding():
    assert format_duration(7325) == "2:02:05"
    assert format_duration(9) == "0:09"


def test_error_contracts():
    with pytest.raises(ValueError):
        format_duration(True)
    with pytest.raises(ValueError):
        format_duration(False)
    with pytest.raises(ValueError):
        format_duration(1.0)
    with pytest.raises(ValueError):
        format_duration("60")
    with pytest.raises(ValueError):
        format_duration(None)
