import pytest
from solution import interval_subtract as f
def test_middle_bite(): assert f([[1, 10]], [[3, 5]]) == [[1, 2], [6, 10]]
def test_one_b_two_a(): assert f([[1, 3], [6, 9]], [[2, 7]]) == [[1, 1], [8, 9]]
def test_exact_removal(): assert f([[1, 5]], [[1, 5]]) == []
def test_empty_b(): assert f([[1, 5]], []) == [[1, 5]]
def test_empty_a(): assert f([], [[1, 2]]) == []
def test_touching(): assert f([[1, 5]], [[5, 9]]) == [[1, 4]]
def test_b_between(): assert f([[0, 3], [5, 8]], [[4, 4]]) == [[0, 3], [5, 8]]
def test_b_spans_all(): assert f([[1, 2], [4, 5]], [[0, 10]]) == []
def test_bad_interval():
    with pytest.raises(ValueError) as e: f([[5, 1]], [])
    assert str(e.value) == 'bad interval'
