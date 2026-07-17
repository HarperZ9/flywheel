import pytest
from solution import natural_compare as f
def test_numeric(): assert f('a2', 'a10') == -1
def test_numeric_gt(): assert f('a10', 'a2') == 1
def test_file(): assert f('file9', 'file10') == -1
def test_equal(): assert f('abc', 'abc') == 0
def test_prefix(): assert f('a', 'a1') == -1
def test_leading_zero(): assert f('01', '1') == 1
def test_digit_before_alpha(): assert f('1', 'a') == -1
def test_plain_alpha(): assert f('a', 'b') == -1
def test_bad_input():
    with pytest.raises(ValueError) as e: f(1, 'a')
    assert str(e.value) == 'bad input'
