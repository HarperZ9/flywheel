import pytest
from solution import parse_money as f
def test_grouped(): assert f('1,234.56') == 123456
def test_cents_only(): assert f('0.99') == 99
def test_negative(): assert f('-12') == -1200
def test_million(): assert f('1,000,000') == 100000000
def test_negative_zero(): assert f('-0.00') == 0
def test_zero(): assert f('0') == 0
def test_leading_zeros():
    with pytest.raises(ValueError) as e: f('007')
    assert str(e.value) == 'bad amount'
def test_bad_group():
    with pytest.raises(ValueError): f('1,23.45')
def test_no_integer_part():
    with pytest.raises(ValueError): f('.50')
def test_one_decimal():
    with pytest.raises(ValueError): f('1.5')
def test_plus():
    with pytest.raises(ValueError): f('+1')
def test_zero_grouped():
    with pytest.raises(ValueError): f('0,123')
