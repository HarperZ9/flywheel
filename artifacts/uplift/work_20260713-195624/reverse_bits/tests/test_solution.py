import pytest
from solution import reverse_bits as f
def test_one_eight(): assert f(1, 8) == 128
def test_ten_four(): assert f(0b1010, 4) == 0b0101
def test_zero(): assert f(0, 4) == 0
def test_six_three(): assert f(0b110, 3) == 0b011
def test_one_one(): assert f(1, 1) == 1
def test_all_ones(): assert f(0b1111, 4) == 0b1111
def test_overflow():
    with pytest.raises(ValueError) as e: f(16, 4)
    assert str(e.value) == 'overflow'
def test_bad_width():
    with pytest.raises(ValueError) as e: f(1, 0)
    assert str(e.value) == 'bad arg'
def test_bad_neg():
    with pytest.raises(ValueError): f(-1, 4)
def test_bool():
    with pytest.raises(ValueError): f(True, 4)
