import pytest
from solution import rotate as f
def test_basic(): assert f([1, 2, 3, 4, 5], 2) == [4, 5, 1, 2, 3]
def test_zero(): assert f([1, 2, 3], 0) == [1, 2, 3]
def test_full_wrap(): assert f([1, 2, 3], 3) == [1, 2, 3]
def test_over_wrap(): assert f([1, 2, 3], 4) == [3, 1, 2]
def test_negative(): assert f([1, 2, 3], -1) == [2, 3, 1]
def test_empty(): assert f([], 5) == []
def test_no_mutation():
    g = [1, 2, 3]
    f(g, 1)
    assert g == [1, 2, 3]
def test_bad_input():
    with pytest.raises(ValueError) as e: f('ab', 1)
    assert str(e.value) == 'bad input'
def test_bad_shift():
    with pytest.raises(ValueError) as e: f([1], True)
    assert str(e.value) == 'bad shift'
