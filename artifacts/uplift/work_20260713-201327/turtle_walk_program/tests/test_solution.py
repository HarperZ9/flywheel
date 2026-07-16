import pytest
from solution import turtle as f
def test_empty(): assert f('') == (0, 0, 'N')
def test_walk(): assert f('2FR3F') == (3, 2, 'E')
def test_backward(): assert f('B') == (0, -1, 'N')
def test_double_left(): assert f('2L') == (0, 0, 'S')
def test_multidigit(): assert f('10F') == (0, 10, 'N')
def test_full_circle(): assert f('LLLL') == (0, 0, 'N')
def test_zero_count():
    with pytest.raises(ValueError) as e: f('0F')
    assert str(e.value) == 'bad count'
def test_leading_zero_count():
    with pytest.raises(ValueError) as e: f('07F')
    assert str(e.value) == 'bad count'
def test_dangling():
    with pytest.raises(ValueError) as e: f('F12')
    assert str(e.value) == 'dangling count'
def test_unknown():
    with pytest.raises(ValueError) as e: f('FxF')
    assert str(e.value) == 'bad command'
