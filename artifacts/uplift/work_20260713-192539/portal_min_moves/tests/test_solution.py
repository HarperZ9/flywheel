import pytest
from solution import portal_moves as f
def test_plain_walk(): assert f(10, [], 0, 9) == 9
def test_direct_portal(): assert f(10, [(0, 9)], 0, 9) == 1
def test_walk_then_portal(): assert f(10, [(1, 8)], 0, 9) == 3
def test_same_cell(): assert f(5, [], 3, 3) == 0
def test_one_cell(): assert f(1, [], 0, 0) == 0
def test_backward_portal_useless(): assert f(10, [(9, 0)], 0, 9) == 9
def test_one_way(): assert f(10, [(0, 5)], 5, 0) == 5
def test_self_portal(): assert f(6, [(2, 2)], 0, 5) == 5
def test_best_of_two(): assert f(10, [(3, 9), (1, 7)], 0, 9) == 4
def test_duplicate_entry():
    with pytest.raises(ValueError) as e: f(10, [(1, 2), (1, 3)], 0, 9)
    assert str(e.value) == 'duplicate portal'
def test_duplicate_identical():
    with pytest.raises(ValueError) as e: f(10, [(1, 2), (1, 2)], 0, 9)
    assert str(e.value) == 'duplicate portal'
def test_bad_portal_list():
    with pytest.raises(ValueError) as e: f(10, [[1, 2]], 0, 9)
    assert str(e.value) == 'bad portal'
def test_bad_portal_range():
    with pytest.raises(ValueError): f(10, [(1, 10)], 0, 9)
def test_bad_portal_bool():
    with pytest.raises(ValueError): f(10, [(1, True)], 0, 9)
def test_bad_portal_not_list():
    with pytest.raises(ValueError): f(10, 'x', 0, 9)
def test_bad_n():
    with pytest.raises(ValueError) as e: f(0, [], 0, 0)
    assert str(e.value) == 'bad n'
def test_bad_n_bool():
    with pytest.raises(ValueError): f(True, [], 0, 0)
def test_bad_cell_range():
    with pytest.raises(ValueError) as e: f(5, [], 5, 0)
    assert str(e.value) == 'bad cell'
def test_bad_cell_bool():
    with pytest.raises(ValueError): f(5, [], True, 0)
