import pytest
from solution import tour_length as f
def test_pair(): assert f([(0, 0), (3, 4)]) == 7
def test_empty(): assert f([]) == 0
def test_single(): assert f([(1, 1)]) == 0
def test_l_shape(): assert f([(0, 0), (0, 5), (5, 5)]) == 10
def test_negative(): assert f([(0, 0), (-3, 0)]) == 3
def test_round_trip(): assert f([(0, 0), (1, 1), (0, 0)]) == 4
def test_bad_list():
    with pytest.raises(ValueError) as e: f([[0, 0]])
    assert str(e.value) == 'bad point'
def test_bad_len():
    with pytest.raises(ValueError): f([(0, 0, 0)])
def test_bool_coord():
    with pytest.raises(ValueError): f([(0, True)])
