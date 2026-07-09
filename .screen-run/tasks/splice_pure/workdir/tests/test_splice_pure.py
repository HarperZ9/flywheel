import pytest
from solution import splice


def test_basic_replace_is_pure():
    items = [1, 2, 3, 4]
    out = splice(items, 1, 3, [9])
    assert out == [1, 9, 4]
    assert items == [1, 2, 3, 4]
    assert out is not items


def test_start_greater_than_stop_inserts():
    assert splice([1, 2, 3], 2, 1, [9]) == [1, 2, 9, 3]


def test_out_of_range_clamps_instead_of_raising():
    assert splice([1, 2, 3], -100, 100, [7]) == [7]
    assert splice([1, 2], 5, 9, [8]) == [1, 2, 8]


def test_negative_indices_normalized():
    assert splice([1, 2, 3, 4], -3, -1, [0]) == [1, 0, 4]


def test_empty_replacement_deletes():
    assert splice([1, 2, 3], 0, 2, []) == [3]


def test_bool_index_rejected():
    with pytest.raises(ValueError):
        splice([1, 2], True, 2, [])
    with pytest.raises(ValueError):
        splice([1, 2], 0, False, [])


def test_non_int_index_rejected():
    with pytest.raises(ValueError):
        splice([1, 2], 0.0, 1, [])


def test_non_list_replacement_rejected():
    with pytest.raises(TypeError):
        splice([1, 2], 0, 1, (9,))
    with pytest.raises(TypeError):
        splice([1, 2], 0, 1, "ab")


def test_no_mutation_and_identity_of_replacement_elements():
    items = [1, 2, 3]
    obj = {"k": 1}
    rep = [obj]
    out = splice(items, 1, 2, rep)
    assert items == [1, 2, 3]
    assert rep == [obj]
    assert out == [1, obj, 3]
    assert out[1] is obj
