import pytest
from solution import gray_rank as f
def test_zero(): assert f('0') == 0
def test_one(): assert f('1') == 1
def test_three_bit_2(): assert f('011') == 2
def test_three_bit_3(): assert f('010') == 3
def test_three_bit_4(): assert f('110') == 4
def test_three_bit_6(): assert f('101') == 6
def test_three_bit_7(): assert f('100') == 7
def test_leading_zeros(): assert f('0011') == 2
def test_roundtrip():
    for i in range(64):
        assert f(format(i ^ (i >> 1), '06b')) == i
def test_empty():
    with pytest.raises(ValueError) as e: f('')
    assert str(e.value) == 'bad code'
def test_bad_char():
    with pytest.raises(ValueError) as e: f('012')
    assert str(e.value) == 'bad code'
def test_not_string():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad code'
