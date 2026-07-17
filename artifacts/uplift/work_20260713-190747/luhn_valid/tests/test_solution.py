import pytest
from solution import luhn_valid as f
def test_single_zero(): assert f('0') is True
def test_eighteen(): assert f('18') is True
def test_seventeen(): assert f('17') is False
def test_classic_valid(): assert f('79927398713') is True
def test_classic_invalid(): assert f('79927398710') is False
def test_twenty_six(): assert f('26') is True
def test_bad_char():
    with pytest.raises(ValueError) as e: f('12a')
    assert str(e.value) == 'bad number'
def test_empty():
    with pytest.raises(ValueError): f('')
def test_not_str():
    with pytest.raises(ValueError): f(18)
