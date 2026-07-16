import pytest
from solution import csv_quote as f
def test_plain(): assert f('abc') == 'abc'
def test_comma(): assert f('a,b') == '"a,b"'
def test_quote(): assert f('a"b') == '"a""b"'
def test_newline(): assert f('a\nb') == '"a\nb"'
def test_empty(): assert f('') == ''
def test_only_quote(): assert f('"') == '""""'
def test_space_plain(): assert f('a b') == 'a b'
def test_carriage(): assert f('a\rb') == '"a\rb"'
def test_bad_field():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad field'
