import pytest
from solution import isbn10_check as f
def test_valid_digits(): assert f('0306406152') is True
def test_valid_x(): assert f('048665088X') is True
def test_invalid(): assert f('0306406153') is False
def test_bad_length():
    with pytest.raises(ValueError) as e: f('123')
    assert str(e.value) == 'bad isbn'
def test_lower_x():
    with pytest.raises(ValueError): f('048665088x')
def test_x_not_last():
    with pytest.raises(ValueError): f('X306406152')
def test_not_str():
    with pytest.raises(ValueError): f(123)
