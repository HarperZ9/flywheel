import pytest
from solution import sliding_window_max as f
def test_classic():
    assert f([1,3,-1,-3,5,3,6,7], 3) == [3,3,5,5,6,7]
def test_k_equals_len():
    assert f([2,1,4], 3) == [4]
def test_k_too_big():
    assert f([1,2], 5) == []
def test_decreasing():
    assert f([5,4,3,2,1], 2) == [5,4,3,2]
def test_duplicates():
    assert f([2,2,2], 2) == [2,2]
def test_bad_k():
    with pytest.raises(ValueError):
        f([1], 0)
