import pytest
from solution import transpose as f
def test_basic(): assert f([[1, 2, 3], [4, 5, 6]]) == [[1, 4], [2, 5], [3, 6]]
def test_column(): assert f([[1], [2], [3]]) == [[1, 2, 3]]
def test_square(): assert f([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]
def test_no_rows(): assert f([]) == []
def test_empty_rows(): assert f([[]]) == []
def test_single(): assert f([[7]]) == [[7]]
def test_ragged():
    with pytest.raises(ValueError) as e: f([[1, 2], [3]])
    assert str(e.value) == 'ragged'
def test_bad_row():
    with pytest.raises(ValueError) as e: f([1, 2])
    assert str(e.value) == 'bad matrix'
def test_bad_matrix():
    with pytest.raises(ValueError): f('x')
