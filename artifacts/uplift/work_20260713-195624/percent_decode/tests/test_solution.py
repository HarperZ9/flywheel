import pytest
from solution import percent_decode as f
def test_space(): assert f('a%20b') == 'a b'
def test_upper_hex(): assert f('%41') == 'A'
def test_percent_literal(): assert f('100%25') == '100%'
def test_plus_literal(): assert f('a+b') == 'a+b'
def test_plain(): assert f('hello') == 'hello'
def test_mixed_case(): assert f('%2F%2f') == '//'
def test_short_escape():
    with pytest.raises(ValueError) as e: f('a%2')
    assert str(e.value) == 'bad escape'
def test_nonhex():
    with pytest.raises(ValueError) as e: f('%2g')
    assert str(e.value) == 'bad escape'
def test_non_ascii():
    with pytest.raises(ValueError) as e: f('%80')
    assert str(e.value) == 'non-ascii byte'
def test_lone_percent():
    with pytest.raises(ValueError): f('%')
