import pytest
from solution import component_count as f
def test_no_edges(): assert f(5, []) == 5
def test_chain(): assert f(5, [(0, 1), (1, 2)]) == 3
def test_two_pairs(): assert f(4, [(0, 1), (2, 3)]) == 2
def test_duplicates(): assert f(3, [(0, 1), (0, 1), (1, 0)]) == 2
def test_self_loop(): assert f(3, [(1, 1)]) == 3
def test_zero_nodes(): assert f(0, []) == 0
def test_cycle(): assert f(4, [(0, 1), (1, 2), (2, 3), (3, 0)]) == 1
def test_bad_n_negative():
    with pytest.raises(ValueError) as e: f(-1, [])
    assert str(e.value) == 'bad n'
def test_bad_n_bool():
    with pytest.raises(ValueError): f(True, [])
def test_bad_edges():
    with pytest.raises(ValueError) as e: f(2, 'x')
    assert str(e.value) == 'bad edges'
def test_bad_edge_list():
    with pytest.raises(ValueError) as e: f(2, [[0, 1]])
    assert str(e.value) == 'bad edge'
def test_bad_edge_len():
    with pytest.raises(ValueError): f(2, [(0,)])
def test_bad_edge_range():
    with pytest.raises(ValueError): f(2, [(0, 2)])
def test_bad_edge_bool():
    with pytest.raises(ValueError): f(2, [(0, True)])
