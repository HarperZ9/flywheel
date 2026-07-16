import pytest
from solution import expand_tabs as f
def test_basic(): assert f('a\tb', 4) == 'a   b'
def test_tab_on_stop(): assert f('abcd\tb', 4) == 'abcd    b'
def test_two_tabs(): assert f('ab\tc\td', 4) == 'ab  c   d'
def test_newline_resets(): assert f('a\nb\tc', 4) == 'a\nb   c'
def test_empty(): assert f('', 4) == ''
def test_stop_one(): assert f('\t', 1) == ' '
def test_bad_stop_zero():
    with pytest.raises(ValueError) as e: f('a', 0)
    assert str(e.value) == 'bad stop'
def test_bad_stop_bool():
    with pytest.raises(ValueError): f('a', True)
