import pytest
from solution import knight_moves as f
def test_one_move(): assert f(8, (0, 0), (1, 2)) == 1
def test_same_cell(): assert f(8, (4, 4), (4, 4)) == 0
def test_one_by_one(): assert f(1, (0, 0), (0, 0)) == 0
def test_corner_to_corner(): assert f(8, (0, 0), (7, 7)) == 6
def test_five_board(): assert f(5, (0, 0), (4, 4)) == 4
def test_three_corner(): assert f(3, (0, 0), (2, 2)) == 4
def test_center_isolated(): assert f(3, (1, 1), (0, 0)) == -1
def test_two_board_unreachable(): assert f(2, (0, 0), (1, 1)) == -1
def test_bad_board_zero():
    with pytest.raises(ValueError) as e: f(0, (0, 0), (0, 0))
    assert str(e.value) == 'bad board'
def test_bad_board_bool():
    with pytest.raises(ValueError): f(True, (0, 0), (0, 0))
def test_bad_cell_list():
    with pytest.raises(ValueError) as e: f(8, [0, 0], (0, 0))
    assert str(e.value) == 'bad cell'
def test_bad_cell_range():
    with pytest.raises(ValueError): f(8, (0, 0), (0, 8))
def test_bad_cell_bool():
    with pytest.raises(ValueError): f(8, (0, True), (0, 0))
def test_bad_cell_len():
    with pytest.raises(ValueError): f(8, (0, 0, 0), (0, 0))
