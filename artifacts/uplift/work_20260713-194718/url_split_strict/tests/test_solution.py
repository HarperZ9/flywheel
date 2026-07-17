import pytest
from solution import split_url as f
def test_basic(): assert f('http://example.com/a/b?x=1') == ('http', 'example.com', None, '/a/b', 'x=1')
def test_no_path(): assert f('http://example.com') == ('http', 'example.com', None, '/', None)
def test_port(): assert f('https://a.b:8080/x') == ('https', 'a.b', 8080, '/x', None)
def test_query_no_path(): assert f('ftp://h?x=2') == ('ftp', 'h', None, '/', 'x=2')
def test_empty_query(): assert f('http://h/p?') == ('http', 'h', None, '/p', '')
def test_second_qmark(): assert f('http://h/p?a?b') == ('http', 'h', None, '/p', 'a?b')
def test_port_zero(): assert f('http://h:0/') == ('http', 'h', 0, '/', None)
def test_max_port(): assert f('http://h:65535') == ('http', 'h', 65535, '/', None)
def test_scheme_chars(): assert f('a+b-c.1://h') == ('a+b-c.1', 'h', None, '/', None)
def test_no_scheme():
    with pytest.raises(ValueError) as e: f('example.com/a')
    assert str(e.value) == 'no scheme'
def test_bad_scheme_upper():
    with pytest.raises(ValueError) as e: f('Http://h')
    assert str(e.value) == 'bad scheme'
def test_bad_scheme_empty():
    with pytest.raises(ValueError): f('://h')
def test_bad_scheme_digit_first():
    with pytest.raises(ValueError): f('1ab://h')
def test_bad_host_empty():
    with pytest.raises(ValueError) as e: f('http://')
    assert str(e.value) == 'bad host'
def test_bad_host_upper():
    with pytest.raises(ValueError): f('http://EXample.com')
def test_bad_port_leading_zero():
    with pytest.raises(ValueError) as e: f('http://h:080')
    assert str(e.value) == 'bad port'
def test_bad_port_too_big():
    with pytest.raises(ValueError): f('http://h:65536')
def test_bad_port_empty():
    with pytest.raises(ValueError): f('http://h:')
def test_bad_port_second_colon():
    with pytest.raises(ValueError): f('http://h:1:2')
def test_bad_url():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad url'
