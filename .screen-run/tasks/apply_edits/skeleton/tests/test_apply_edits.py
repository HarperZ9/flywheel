import pytest
from solution import apply_edits


def test_sequential_ops_on_intermediate_state():
    items = [1, 2, 3]
    out = apply_edits(items, [("insert", 1, 9), ("delete", 0), ("replace", 2, 7)])
    # [1,9,2,3] -> [9,2,3] -> [9,2,7]
    assert out == [9, 2, 7]
    assert items == [1, 2, 3]


def test_insert_at_end_allowed():
    assert apply_edits([1], [("insert", 1, 5)]) == [1, 5]


def test_insert_past_end_raises_index_error_not_clamped():
    with pytest.raises(IndexError):
        apply_edits([1], [("insert", 3, 5)])


def test_negative_indices():
    assert apply_edits([1, 2, 3], [("replace", -1, 9)]) == [1, 2, 9]
    assert apply_edits([1, 2, 3], [("insert", -3, 0)]) == [0, 1, 2, 3]
    with pytest.raises(IndexError):
        apply_edits([1, 2, 3], [("delete", -4)])


def test_unknown_op_raises_value_error():
    with pytest.raises(ValueError):
        apply_edits([1], [("swap", 0, 0)])


def test_malformed_op_raises_value_error():
    with pytest.raises(ValueError):
        apply_edits([1], [["insert", 0, 5]])
    with pytest.raises(ValueError):
        apply_edits([1], [("delete", 0, 1)])
    with pytest.raises(ValueError):
        apply_edits([1], [("insert", 0)])


def test_input_untouched_even_when_error_midway():
    items = [1, 2]
    with pytest.raises(IndexError):
        apply_edits(items, [("insert", 0, 9), ("delete", 5)])
    assert items == [1, 2]


def test_delete_on_empty_raises():
    with pytest.raises(IndexError):
        apply_edits([], [("delete", 0)])
