import pytest
from solution import eval_bool as f
def test_true(): assert f('T') is True
def test_false(): assert f('F') is False
def test_and(): assert f('T&F') is False
def test_or(): assert f('T|F') is True
def test_not(): assert f('!T') is False
def test_not_precedence(): assert f('!F&T') is True
def test_and_before_or(): assert f('T|F&F') is True
def test_parens(): assert f('(T|F)&F') is False
def test_not_group(): assert f('!(T&F)') is True
def test_bad_char():
    with pytest.raises(ValueError) as e: f('T+F')
    assert str(e.value) == 'bad expr'
def test_unbalanced():
    with pytest.raises(ValueError): f('(T')
def test_trailing():
    with pytest.raises(ValueError): f('TT')
def test_empty():
    with pytest.raises(ValueError): f('')
