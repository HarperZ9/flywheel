import pytest
from solution import longest_digit_run as f
def test_zero(): assert f(0) == (0, 1, 0)
def test_single(): assert f(7) == (0, 1, 7)
def test_basic(): assert f(11222) == (2, 3, 2)
def test_front(): assert f(22211) == (0, 3, 2)
def test_tie_leftmost(): assert f(1122) == (0, 2, 1)
def test_zeros(): assert f(1000) == (1, 3, 0)
def test_alternating(): assert f(121212) == (0, 1, 1)
def test_three_way_tie(): assert f(9998887776) == (0, 3, 9)
def test_late_win(): assert f(12333) == (2, 3, 3)
def test_is_tuple(): assert type(f(11)) is tuple
def test_negative():
    with pytest.raises(ValueError) as e: f(-5)
    assert str(e.value) == 'bad number'
def test_bool():
    with pytest.raises(ValueError) as e: f(True)
    assert str(e.value) == 'bad number'
def test_string():
    with pytest.raises(ValueError) as e: f('11')
    assert str(e.value) == 'bad number'
