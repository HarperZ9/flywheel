import pytest
from solution import round_half_even as f
def test_half_down(): assert f(1, 2) == 0
def test_half_up(): assert f(3, 2) == 2
def test_half_even(): assert f(5, 2) == 2
def test_over(): assert f(7, 4) == 2
def test_third(): assert f(1, 3) == 0
def test_neg_half(): assert f(-1, 2) == 0
def test_neg_three_half(): assert f(-3, 2) == -2
def test_exact(): assert f(4, 2) == 2
def test_neg_den(): assert f(5, -2) == -2
def test_div_zero():
    with pytest.raises(ValueError) as e: f(1, 0)
    assert str(e.value) == 'div by zero'
def test_bad_arg():
    with pytest.raises(ValueError) as e: f(True, 2)
    assert str(e.value) == 'bad arg'
