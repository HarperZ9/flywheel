import pytest
from solution import sliding_windows as f
def test_step_one(): assert f([1, 2, 3, 4], 2, 1) == [[1, 2], [2, 3], [3, 4]]
def test_step_two(): assert f([1, 2, 3, 4, 5], 2, 2) == [[1, 2], [3, 4]]
def test_full(): assert f([1, 2, 3], 3, 1) == [[1, 2, 3]]
def test_too_big(): assert f([1, 2], 3, 1) == []
def test_overlap(): assert f([1, 2, 3, 4, 5], 3, 2) == [[1, 2, 3], [3, 4, 5]]
def test_empty(): assert f([], 1, 1) == []
def test_bad_size():
    with pytest.raises(ValueError) as e: f([1], 0, 1)
    assert str(e.value) == 'bad size'
def test_bad_step():
    with pytest.raises(ValueError) as e: f([1], 1, 0)
    assert str(e.value) == 'bad step'
def test_bad_input():
    with pytest.raises(ValueError) as e: f('ab', 1, 1)
    assert str(e.value) == 'bad input'
