import pytest
from solution import perm_rank as f
def test_empty(): assert f([]) == 0
def test_single(): assert f([0]) == 0
def test_identity(): assert f([0, 1, 2]) == 0
def test_reversed(): assert f([2, 1, 0]) == 5
def test_middle(): assert f([1, 0, 2]) == 2
def test_middle2(): assert f([1, 2, 0]) == 3
def test_larger(): assert f([3, 1, 4, 2, 0]) == 83
def test_missing():
    with pytest.raises(ValueError) as e: f([0, 2])
    assert str(e.value) == 'not a permutation'
def test_duplicate():
    with pytest.raises(ValueError) as e: f([0, 0])
    assert str(e.value) == 'not a permutation'
def test_bad_element():
    with pytest.raises(ValueError) as e: f([0.5])
    assert str(e.value) == 'bad element'
def test_bool_element():
    with pytest.raises(ValueError) as e: f([True, 0])
    assert str(e.value) == 'bad element'
def test_bad_input():
    with pytest.raises(ValueError) as e: f('012')
    assert str(e.value) == 'bad input'
