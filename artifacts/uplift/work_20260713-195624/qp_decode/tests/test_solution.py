import pytest
from solution import qp_decode as f
def test_plain(): assert f('hello world') == 'hello world'
def test_space(): assert f('a=20b') == 'a b'
def test_equals(): assert f('=3D') == '='
def test_letters(): assert f('=41=42') == 'AB'
def test_soft_lf(): assert f('foo=\nbar') == 'foobar'
def test_soft_crlf(): assert f('foo=\r\nbar') == 'foobar'
def test_hard_newline(): assert f('a\nb') == 'a\nb'
def test_high_byte(): assert f('=FF') == '\xff'
def test_newline_escape(): assert f('=0A') == '\n'
def test_empty(): assert f('') == ''
def test_lowercase():
    with pytest.raises(ValueError) as e: f('=3d')
    assert str(e.value) == 'bad escape'
def test_trailing():
    with pytest.raises(ValueError) as e: f('abc=')
    assert str(e.value) == 'bad escape'
def test_one_digit():
    with pytest.raises(ValueError): f('=4')
def test_bad_hex():
    with pytest.raises(ValueError): f('=G1')
def test_cr_only():
    with pytest.raises(ValueError): f('a=\rb')
def test_bad_input():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad input'
