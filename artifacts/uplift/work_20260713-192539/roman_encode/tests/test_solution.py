import pytest
from solution import to_roman as f
def test_four(): assert f(4) == 'IV'
def test_nine(): assert f(9) == 'IX'
def test_fifty_eight(): assert f(58) == 'LVIII'
def test_big(): assert f(1994) == 'MCMXCIV'
def test_max(): assert f(3999) == 'MMMCMXCIX'
def test_one(): assert f(1) == 'I'
def test_forty(): assert f(40) == 'XL'
def test_below():
    with pytest.raises(ValueError) as e: f(0)
    assert str(e.value) == 'out of range'
def test_above():
    with pytest.raises(ValueError): f(4000)
def test_bool():
    with pytest.raises(ValueError): f(True)
