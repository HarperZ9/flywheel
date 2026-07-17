import pytest
from solution import json_escape as f
def test_quote(): assert f('a"b') == 'a\\"b'
def test_backslash(): assert f('a\\b') == 'a\\\\b'
def test_newline(): assert f('x\ny') == 'x\\ny'
def test_tab(): assert f('\t') == '\\t'
def test_backspace(): assert f(chr(8)) == '\\b'
def test_formfeed(): assert f(chr(12)) == '\\f'
def test_ctrl_zero(): assert f(chr(0)) == '\\u0000'
def test_ctrl_31(): assert f(chr(31)) == '\\u001f'
def test_plain(): assert f('hello') == 'hello'
def test_bad_input():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad input'
