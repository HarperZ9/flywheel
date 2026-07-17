import pytest
from solution import to_base as f
def test_hex(): assert f(255, 16) == 'ff'
def test_zero(): assert f(0, 2) == '0'
def test_binary(): assert f(10, 2) == '1010'
def test_negative(): assert f(-31, 16) == '-1f'
def test_top_digit(): assert f(35, 36) == 'z'
def test_rollover(): assert f(36, 36) == '10'
def test_bad_base_low():
    with pytest.raises(ValueError) as e: f(5, 1)
    assert str(e.value) == 'bad base'
def test_bad_base_high():
    with pytest.raises(ValueError): f(5, 37)
def test_bad_base_bool():
    with pytest.raises(ValueError) as e: f(5, True)
    assert str(e.value) == 'bad base'
def test_bad_number_bool():
    with pytest.raises(ValueError) as e: f(True, 2)
    assert str(e.value) == 'bad number'
