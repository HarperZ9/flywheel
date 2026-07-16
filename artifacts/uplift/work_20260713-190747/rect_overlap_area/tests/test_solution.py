import pytest
from solution import rect_overlap as f
def test_overlap(): assert f((0, 0, 4, 4), (2, 2, 6, 6)) == 4
def test_nested(): assert f((0, 0, 10, 10), (2, 3, 4, 5)) == 4
def test_touching_edge(): assert f((0, 0, 2, 2), (2, 0, 4, 2)) == 0
def test_disjoint(): assert f((0, 0, 1, 1), (5, 5, 6, 6)) == 0
def test_degenerate(): assert f((0, 0, 0, 5), (0, 0, 5, 5)) == 0
def test_negative_coords(): assert f((-3, -3, 1, 1), (-1, -1, 0, 0)) == 1
def test_list_rejected():
    with pytest.raises(ValueError) as e: f([0, 0, 1, 1], (0, 0, 1, 1))
    assert str(e.value) == 'bad rect'
def test_inverted():
    with pytest.raises(ValueError): f((1, 0, 0, 1), (0, 0, 1, 1))
def test_bool_coord():
    with pytest.raises(ValueError): f((0, 0, True, 1), (0, 0, 1, 1))
