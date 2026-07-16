import pytest
from solution import parse_kv as f
def test_basic(): assert f('a=1;b=2') == [('a', '1'), ('b', '2')]
def test_empty(): assert f('') == []
def test_empty_value(): assert f('x=') == [('x', '')]
def test_underscore(): assert f('key_1=val') == [('key_1', 'val')]
def test_duplicate():
    with pytest.raises(ValueError) as e: f('a=1;a=2')
    assert str(e.value) == 'duplicate key'
def test_no_equals():
    with pytest.raises(ValueError) as e: f('a')
    assert str(e.value) == 'bad item'
def test_empty_key():
    with pytest.raises(ValueError): f('=v')
def test_two_equals():
    with pytest.raises(ValueError): f('a=b=c')
def test_trailing_semicolon():
    with pytest.raises(ValueError): f('a=1;')
def test_bad_key_char():
    with pytest.raises(ValueError): f('a b=1')
def test_bad_input():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad input'
