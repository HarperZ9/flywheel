import pytest
from solution import reduce_fraction as f
def test_basic(): assert f(4, 8) == (1, 2)
def test_neg_num(): assert f(-4, 8) == (-1, 2)
def test_neg_den(): assert f(4, -8) == (-1, 2)
def test_both_neg(): assert f(-4, -8) == (1, 2)
def test_zero(): assert f(0, 5) == (0, 1)
def test_already(): assert f(7, 1) == (7, 1)
def test_reduce_int(): assert f(6, 3) == (2, 1)
def test_div_zero():
    with pytest.raises(ValueError) as e: f(1, 0)
    assert str(e.value) == 'div by zero'
def test_bad_arg():
    with pytest.raises(ValueError) as e: f(True, 2)
    assert str(e.value) == 'bad arg'
