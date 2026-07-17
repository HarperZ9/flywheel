import pytest
from solution import multiset_diff as f
def test_basic(): assert f([1, 1, 2, 3], [1, 3]) == [1, 2]
def test_repeat(): assert f([1, 1, 1], [1]) == [1, 1]
def test_disjoint(): assert f([1, 2, 3], [4, 5]) == [1, 2, 3]
def test_all_removed(): assert f([1, 2], [1, 2, 3]) == []
def test_empty_a(): assert f([], [1]) == []
def test_sorted_out(): assert f([3, 1, 2, 2], []) == [1, 2, 2, 3]
def test_bad_item_bool():
    with pytest.raises(ValueError) as e: f([True], [])
    assert str(e.value) == 'bad item'
def test_bad_item_float():
    with pytest.raises(ValueError): f([1], [1.5])
