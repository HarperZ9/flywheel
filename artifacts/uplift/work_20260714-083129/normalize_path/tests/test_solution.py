import pytest
from solution import normalize_path as f
def test_plain(): assert f('/a/b/c') == '/a/b/c'
def test_double_slash(): assert f('/a//b') == '/a/b'
def test_dot(): assert f('/a/./b') == '/a/b'
def test_dotdot(): assert f('/a/b/../c') == '/a/c'
def test_root(): assert f('/') == '/'
def test_above_root(): assert f('/..') == '/'
def test_collapse_all(): assert f('/a/../..') == '/'
def test_trailing(): assert f('/a/b/') == '/a/b'
def test_dotdot_from_root(): assert f('/../a') == '/a'
def test_not_absolute():
    with pytest.raises(ValueError) as e: f('a/b')
    assert str(e.value) == 'not absolute'
def test_bad_path():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad path'
