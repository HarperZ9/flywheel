import pytest
from solution import split_identifier as f
def test_acronym_then_word(): assert f('HTTPServer2Node') == ['HTTP', 'Server', '2', 'Node']
def test_camel_acronym(): assert f('parseJSON2XML') == ['parse', 'JSON', '2', 'XML']
def test_snake(): assert f('snake_case_two') == ['snake', 'case', 'two']
def test_underscore_trim(): assert f('__x__') == ['x']
def test_empty(): assert f('') == []
def test_two_caps_then_lower(): assert f('ABc') == ['A', 'Bc']
def test_plain(): assert f('simple') == ['simple']
def test_single_cap_then_digit(): assert f('A1a') == ['A', '1', 'a']
def test_bad_char():
    with pytest.raises(ValueError) as e: f('a-b')
    assert str(e.value) == 'bad char'
