import pytest
from solution import parse_ini as f
def test_basic():
    assert f('[db]\nhost=local\nport=5432') == {'db': {'host': 'local', 'port': '5432'}}
def test_two_sections():
    assert f('[a]\nx=1\n[b]\nx=2') == {'a': {'x': '1'}, 'b': {'x': '2'}}
def test_comments_blank():
    assert f('; c\n\n[s]\n# c\nk=v\n') == {'s': {'k': 'v'}}
def test_whitespace():
    assert f('  [s]  \n  k  =  v  ') == {'s': {'k': 'v'}}
def test_value_with_equals():
    assert f('[s]\nk=a=b') == {'s': {'k': 'a=b'}}
def test_empty_value():
    assert f('[s]\nk=') == {'s': {'k': ''}}
def test_empty_section_body():
    assert f('[s]') == {'s': {}}
def test_empty_text():
    assert f('') == {}
def test_same_key_other_section():
    assert f('[a]\nk=1\n[b]\nk=2') == {'a': {'k': '1'}, 'b': {'k': '2'}}
def test_no_section():
    with pytest.raises(ValueError) as e: f('k=v')
    assert str(e.value) == 'no section'
def test_duplicate_key():
    with pytest.raises(ValueError) as e: f('[s]\nk=1\nk=2')
    assert str(e.value) == 'duplicate key'
def test_duplicate_section():
    with pytest.raises(ValueError) as e: f('[s]\nk=1\n[s]\nj=2')
    assert str(e.value) == 'duplicate section'
def test_bad_section_unclosed():
    with pytest.raises(ValueError) as e: f('[s')
    assert str(e.value) == 'bad section'
def test_bad_section_empty():
    with pytest.raises(ValueError): f('[]')
def test_bad_line_no_equals():
    with pytest.raises(ValueError) as e: f('[s]\nnovalue')
    assert str(e.value) == 'bad line'
def test_bad_key_char():
    with pytest.raises(ValueError): f('[s]\na b=1')
def test_bad_input():
    with pytest.raises(ValueError) as e: f(5)
    assert str(e.value) == 'bad input'
