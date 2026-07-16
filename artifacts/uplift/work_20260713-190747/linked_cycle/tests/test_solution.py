import pytest
from solution import has_cycle as f
def test_empty(): assert f([]) is False
def test_terminates(): assert f([-1]) is False
def test_self_loop(): assert f([0]) is True
def test_chain(): assert f([1, 2, -1]) is False
def test_cycle(): assert f([1, 2, 0]) is True
def test_unreached_end(): assert f([1, -1, 1]) is False
def test_reachable_cycle(): assert f([2, 2, 1]) is True
def test_out_of_range():
    with pytest.raises(ValueError) as e: f([5])
    assert str(e.value) == 'bad link'
def test_below_neg_one():
    with pytest.raises(ValueError): f([-2])
def test_bool():
    with pytest.raises(ValueError): f([True])
