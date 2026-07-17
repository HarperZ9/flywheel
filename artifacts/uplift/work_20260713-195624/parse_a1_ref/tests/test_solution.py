import pytest
from solution import parse_a1 as f
def test_a1(): assert f('A1') == (1, 1)
def test_b2(): assert f('B2') == (2, 2)
def test_z10(): assert f('Z10') == (10, 26)
def test_aa1(): assert f('AA1') == (1, 27)
def test_ab100(): assert f('AB100') == (100, 28)
def test_no_digits():
    with pytest.raises(ValueError) as e: f('AB')
    assert str(e.value) == 'bad ref'
def test_no_letters():
    with pytest.raises(ValueError): f('12')
def test_lowercase():
    with pytest.raises(ValueError): f('a1')
def test_leading_zero():
    with pytest.raises(ValueError): f('A01')
def test_zero_row():
    with pytest.raises(ValueError): f('A0')
def test_letters_after_digits():
    with pytest.raises(ValueError): f('A1B')
