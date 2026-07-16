import pytest
from solution import path_steps as f
def test_open_two(): assert f([[0, 0], [0, 0]]) == 2
def test_single_open(): assert f([[0]]) == 0
def test_single_wall(): assert f([[1]]) == -1
def test_blocked(): assert f([[0, 1], [1, 0]]) == -1
def test_detour(): assert f([[0, 0, 0], [1, 1, 0], [0, 0, 0]]) == 4
def test_row(): assert f([[0, 0, 0, 0]]) == 3
def test_start_wall(): assert f([[1, 0], [0, 0]]) == -1
def test_goal_wall(): assert f([[0, 0], [0, 1]]) == -1
def test_ragged():
    with pytest.raises(ValueError) as e: f([[0, 0], [0]])
    assert str(e.value) == 'ragged'
def test_ragged_before_cell():
    with pytest.raises(ValueError) as e: f([[0, 2], [0]])
    assert str(e.value) == 'ragged'
def test_bad_cell_two():
    with pytest.raises(ValueError) as e: f([[0, 2]])
    assert str(e.value) == 'bad cell'
def test_bad_cell_bool():
    with pytest.raises(ValueError): f([[0, True]])
def test_bad_grid_empty():
    with pytest.raises(ValueError) as e: f([])
    assert str(e.value) == 'bad grid'
def test_bad_grid_empty_row():
    with pytest.raises(ValueError): f([[]])
def test_bad_grid_not_list():
    with pytest.raises(ValueError): f('grid')
def test_bad_grid_flat():
    with pytest.raises(ValueError): f([0, 1])
