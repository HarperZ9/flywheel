import pytest
from solution import uniq_counts as f
def test_basic(): assert f([1, 1, 2, 3, 3, 3]) == [[1, 2], [2, 1], [3, 3]]
def test_empty(): assert f([]) == []
def test_strings(): assert f(['a', 'a', 'b']) == [['a', 2], ['b', 1]]
def test_single(): assert f([5]) == [[5, 1]]
def test_reappear(): assert f([1, 2, 1]) == [[1, 1], [2, 1], [1, 1]]
def test_type_guard(): assert f([1, True]) == [[1, 1], [True, 1]]
def test_bad_input():
    with pytest.raises(ValueError) as e: f('aa')
    assert str(e.value) == 'bad input'
