import pytest
from solution import purge_in_place


def test_removes_and_counts():
    items = [1, 2, 3, 2, 4, 2]
    n = purge_in_place(items, [2, 4])
    assert n == 4
    assert items == [1, 3]


def test_in_place_mutation_visible_to_alias():
    items = [1, 2, 3]
    alias = items
    result = purge_in_place(items, [2])
    assert alias == [1, 3]
    assert isinstance(result, int)


def test_type_strict_int_target_ignores_bool_and_float():
    items = [1, True, 0, False, 1.0]
    n = purge_in_place(items, [1])
    assert items == [True, 0, False, 1.0]
    assert n == 1


def test_type_strict_bool_target_ignores_int():
    items = [1, True, 1.0]
    n = purge_in_place(items, [True])
    assert items == [1, 1.0]
    assert n == 1


def test_type_strict_float_target_ignores_int():
    items = [1.0, 1]
    assert purge_in_place(items, [1.0]) == 1
    assert items == [1]


def test_aliasing_raises_and_leaves_list_alone():
    items = [1, 2]
    with pytest.raises(ValueError):
        purge_in_place(items, items)
    assert items == [1, 2]


def test_targets_not_mutated():
    targets = [2]
    items = [2, 2]
    purge_in_place(items, targets)
    assert targets == [2]


def test_empty_targets():
    items = [1, 2]
    assert purge_in_place(items, []) == 0
    assert items == [1, 2]


def test_order_of_survivors_preserved():
    items = [5, 9, 5, 3, 9, 7]
    purge_in_place(items, [9])
    assert items == [5, 5, 3, 7]
