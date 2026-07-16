import pytest
from solution import outline_number as f
def test_basic():
    assert f(['# A', '## B', '## C', '# D']) == ['1 A', '1.1 B', '1.2 C', '2 D']
def test_deep_reset():
    assert f(['# A', '## B', '### C', '## D', '### E']) == ['1 A', '1.1 B', '1.1.1 C', '1.2 D', '1.2.1 E']
def test_ignore_nonheaders():
    assert f(['text', '# A', 'more', '## B']) == ['1 A', '1.1 B']
def test_empty(): assert f([]) == []
def test_no_headers(): assert f(['just', 'text']) == []
def test_jump_shallow():
    assert f(['# A', '## B', '### C', '# D']) == ['1 A', '1.1 B', '1.1.1 C', '2 D']
def test_title_with_hash(): assert f(['# A # B']) == ['1 A # B']
def test_first_not_level1():
    with pytest.raises(ValueError) as e: f(['## A'])
    assert str(e.value) == 'bad nesting'
def test_skip_level():
    with pytest.raises(ValueError) as e: f(['# A', '### C'])
    assert str(e.value) == 'bad nesting'
def test_seven_hashes():
    with pytest.raises(ValueError) as e: f(['####### X'])
    assert str(e.value) == 'bad header'
def test_no_space():
    with pytest.raises(ValueError): f(['#title'])
def test_empty_title():
    with pytest.raises(ValueError): f(['# '])
def test_double_space():
    with pytest.raises(ValueError): f(['#  x'])
def test_bad_input():
    with pytest.raises(ValueError) as e: f('# A')
    assert str(e.value) == 'bad input'
def test_bad_element():
    with pytest.raises(ValueError): f([1])
