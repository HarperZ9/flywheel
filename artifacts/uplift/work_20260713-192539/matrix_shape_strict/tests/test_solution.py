import pytest
from solution import matrix_shape as f
def test_shape(): assert f([[1, 2, 3], [4, 5, 6]]) == (2, 3)
def test_float_cell(): assert f([[1.5]]) == (1, 1)
def test_not_list():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'not a list'
def test_empty():
    with pytest.raises(ValueError) as e: f([])
    assert str(e.value) == 'empty'
def test_row_not_list():
    with pytest.raises(ValueError) as e: f([[1], (2,)])
    assert str(e.value) == 'row not list'
def test_empty_row():
    with pytest.raises(ValueError) as e: f([[1], []])
    assert str(e.value) == 'empty row'
def test_ragged():
    with pytest.raises(ValueError) as e: f([[1, 2], [3]])
    assert str(e.value) == 'ragged'
def test_bad_cell():
    with pytest.raises(ValueError) as e: f([[1, True]])
    assert str(e.value) == 'bad cell'
def test_cell_before_later_ragged():
    with pytest.raises(ValueError) as e: f([[1, 'x'], [2]])
    assert str(e.value) == 'bad cell'
def test_ragged_before_own_cells():
    with pytest.raises(ValueError) as e: f([[1, 2], [3, 'x', 4]])
    assert str(e.value) == 'ragged'
