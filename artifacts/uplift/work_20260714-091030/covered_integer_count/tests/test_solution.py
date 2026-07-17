import pytest
from solution import count_covered as f
def test_overlap(): assert f([[1, 3], [2, 5]]) == 5
def test_adjacent(): assert f([[1, 2], [3, 4]]) == 4
def test_empty(): assert f([]) == 0
def test_duplicates(): assert f([[1, 1], [1, 1]]) == 1
def test_negative(): assert f([[-5, -3], [10, 10]]) == 4
def test_no_mutation():
    g = [[5, 7], [1, 2]]
    assert f(g) == 5
    assert g == [[5, 7], [1, 2]]
def test_inverted():
    with pytest.raises(ValueError) as e: f([[3, 1]])
    assert str(e.value) == 'bad interval'
def test_bool_bound():
    with pytest.raises(ValueError): f([[True, 2]])
