import pytest
from solution import top_k as f
def test_basic(): assert f(['a', 'b', 'a', 'c', 'b', 'a'], 2) == ['a', 'b']
def test_all_tie(): assert f(['a', 'b', 'c'], 2) == ['a', 'b']
def test_k_exceeds(): assert f(['b', 'a'], 5) == ['a', 'b']
def test_empty(): assert f([], 3) == []
def test_k_zero(): assert f(['x', 'x'], 0) == []
def test_tie_break(): assert f(['z', 'a', 'z', 'a'], 1) == ['a']
def test_bad_k():
    with pytest.raises(ValueError) as e: f([], -1)
    assert str(e.value) == 'bad k'
def test_bad_item():
    with pytest.raises(ValueError) as e: f([1, 2], 1)
    assert str(e.value) == 'bad item'
def test_bool_k():
    with pytest.raises(ValueError): f([], True)
