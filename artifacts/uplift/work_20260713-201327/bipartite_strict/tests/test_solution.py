import pytest
from solution import is_bipartite as f
def test_empty(): assert f([]) is True
def test_single_edge(): assert f([[1], [0]]) is True
def test_triangle(): assert f([[1, 2], [0, 2], [0, 1]]) is False
def test_isolated(): assert f([[], [], []]) is True
def test_self_loop(): assert f([[0]]) is False
def test_even_cycle(): assert f([[1, 3], [0, 2], [1, 3], [2, 0]]) is True
def test_odd_component(): assert f([[1], [0], [3, 4], [2, 4], [2, 3]]) is False
def test_duplicate_neighbors(): assert f([[1, 1], [0]]) is True
def test_not_symmetric():
    with pytest.raises(ValueError) as e: f([[1], []])
    assert str(e.value) == 'not symmetric'
def test_bad_neighbor_range():
    with pytest.raises(ValueError) as e: f([[5]])
    assert str(e.value) == 'bad neighbor'
def test_bad_neighbor_bool():
    with pytest.raises(ValueError): f([[True], [0]])
def test_bad_neighbor_negative():
    with pytest.raises(ValueError): f([[-1]])
def test_bad_adjacency_not_list():
    with pytest.raises(ValueError) as e: f('x')
    assert str(e.value) == 'bad adjacency'
def test_bad_adjacency_entry():
    with pytest.raises(ValueError): f([1])
