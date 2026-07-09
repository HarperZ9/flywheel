import pytest
from solution import partition_three


def test_stable_three_way():
    lst = [5, 1, 4, 2, 9, 4, 3]
    out = partition_three(lst, 4)
    assert out == [1, 2, 3, 4, 4, 5, 9]


def test_stability_observable_in_groups():
    lst = [9, 5, 7, 1, 3, 2]
    partition_three(lst, 4)
    assert lst == [1, 3, 2, 9, 5, 7]


def test_in_place_same_object():
    lst = [3, 1, 2]
    out = partition_three(lst, 2)
    assert out is lst
    assert lst == [1, 2, 3]


def test_rejects_bool_element_and_leaves_input_unchanged():
    lst = [3, True, 1]
    with pytest.raises(ValueError):
        partition_three(lst, 2)
    assert lst == [3, True, 1]


def test_rejects_float_element_and_leaves_input_unchanged():
    lst = [1, 2.0, 3]
    with pytest.raises(ValueError):
        partition_three(lst, 2)
    assert lst == [1, 2.0, 3]


def test_rejects_non_int_pivot():
    with pytest.raises(ValueError):
        partition_three([1, 2], 1.5)


def test_rejects_bool_pivot():
    with pytest.raises(ValueError):
        partition_three([1, 2], True)


def test_empty_list():
    lst = []
    assert partition_three(lst, 0) is lst
    assert lst == []
