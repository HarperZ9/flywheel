import pytest
from solution import parse_duration_strict


def test_full_form():
    assert parse_duration_strict("1h30m15s") == 5415
    assert parse_duration_strict("2h0m1s") == 7201


def test_single_units():
    assert parse_duration_strict("2h") == 7200
    assert parse_duration_strict("10m") == 600
    assert parse_duration_strict("45s") == 45


def test_leading_component_unbounded():
    assert parse_duration_strict("90m") == 5400
    assert parse_duration_strict("120s") == 120
    assert parse_duration_strict("1000h") == 3600000
    assert parse_duration_strict("61m59s") == 3719


def test_zero_values():
    assert parse_duration_strict("0s") == 0
    assert parse_duration_strict("0h") == 0
    assert parse_duration_strict("1h0m0s") == 3600


def test_order_and_duplicate_raise():
    for bad in ["5m1h", "10s5m", "1h2h", "5s5s", "3s2h"]:
        with pytest.raises(ValueError):
            parse_duration_strict(bad)


def test_range_raise():
    for bad in ["1h60m", "1m60s", "1h30m60s", "2h75m"]:
        with pytest.raises(ValueError):
            parse_duration_strict(bad)


def test_leading_zero_raise():
    for bad in ["05m", "00s", "1h05s", "0h00m"]:
        with pytest.raises(ValueError):
            parse_duration_strict(bad)


def test_malformed_raise():
    for bad in ["", "h", "5", "5x", "5M", "5m3", "1.5h", "-5m", " 5m", "5m ", "5 m"]:
        with pytest.raises(ValueError):
            parse_duration_strict(bad)
