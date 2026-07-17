import pytest
from solution import merge_tallies


def test_sums_counts():
    assert merge_tallies({"a": 2, "b": 1}, {"a": 3}) == {"a": 5, "b": 1}


def test_drops_zero_totals():
    out = merge_tallies({"a": 2, "b": 1}, {"a": -2, "c": 0})
    assert out == {"b": 1}


def test_zero_only_in_a_dropped():
    assert merge_tallies({"a": 0}, {"b": 2}) == {"b": 2}


def test_key_order_a_then_b_only():
    out = merge_tallies({"x": 1, "y": 2}, {"z": 3, "y": 1, "w": 4})
    assert list(out) == ["x", "y", "z", "w"]
    assert out == {"x": 1, "y": 3, "z": 3, "w": 4}


def test_inputs_not_mutated_and_new_dict():
    a = {"a": 1}
    b = {}
    out = merge_tallies(a, b)
    assert out == {"a": 1}
    assert out is not a and out is not b
    assert a == {"a": 1} and b == {}


def test_rejects_bool_count():
    with pytest.raises(ValueError):
        merge_tallies({"a": True}, {})


def test_rejects_float_count():
    with pytest.raises(ValueError):
        merge_tallies({}, {"a": 1.0})


def test_negative_totals_kept():
    assert merge_tallies({"a": -3}, {"a": 1}) == {"a": -2}
