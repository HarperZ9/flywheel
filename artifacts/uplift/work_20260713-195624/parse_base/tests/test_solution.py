import pytest
from solution import from_base as f
def test_hex(): assert f('ff', 16) == 255
def test_upper(): assert f('FF', 16) == 255
def test_binary(): assert f('1010', 2) == 10
def test_negative(): assert f('-1f', 16) == -31
def test_leading_zeros(): assert f('007', 10) == 7
def test_top_digit(): assert f('z', 36) == 35
def test_digit_ge_base():
    with pytest.raises(ValueError) as e: f('12', 2)
    assert str(e.value) == 'bad digits'
def test_empty():
    with pytest.raises(ValueError) as e: f('', 10)
    assert str(e.value) == 'bad digits'
def test_lone_minus():
    with pytest.raises(ValueError): f('-', 10)
def test_plus():
    with pytest.raises(ValueError): f('+5', 10)
def test_bad_base():
    with pytest.raises(ValueError) as e: f('1', 1)
    assert str(e.value) == 'bad base'
