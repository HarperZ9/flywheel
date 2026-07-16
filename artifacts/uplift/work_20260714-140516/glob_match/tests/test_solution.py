import pytest
from solution import glob_match as f
def test_star_ext(): assert f('*.txt', 'file.txt') is True
def test_star_ext_no(): assert f('*.txt', 'file.py') is False
def test_question(): assert f('?at', 'cat') is True
def test_question_zero(): assert f('?at', 'at') is False
def test_star_empty(): assert f('*', '') is True
def test_star_between(): assert f('a*b', 'ab') is True
def test_star_middle(): assert f('a*b', 'aXXb') is True
def test_star_no_tail(): assert f('a*b', 'aXX') is False
def test_empty_both(): assert f('', '') is True
def test_empty_pattern(): assert f('', 'x') is False
def test_bad_input():
    with pytest.raises(ValueError) as e: f(1, 'a')
    assert str(e.value) == 'bad input'
