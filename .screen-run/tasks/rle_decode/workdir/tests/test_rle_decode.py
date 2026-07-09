import pytest
from solution import rle_decode as f
def test_empty():
    assert f('') == ''
def test_simple():
    assert f('3a1b') == 'aaab'
def test_multidigit():
    assert f('12a2b') == 'a'*12 + 'bb'
def test_no_count():
    with pytest.raises(ValueError):
        f('ab')
def test_trailing_count():
    with pytest.raises(ValueError):
        f('3a2')
def test_zero_count():
    with pytest.raises(ValueError):
        f('0a')
