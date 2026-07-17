import pytest
from solution import group_anagrams as f
def test_basic():
    assert f(['eat', 'tea', 'tan', 'ate', 'nat', 'bat']) == [['ate', 'eat', 'tea'], ['bat'], ['nat', 'tan']]
def test_empty(): assert f([]) == []
def test_single(): assert f(['abc']) == [['abc']]
def test_repeat(): assert f(['a', 'b', 'a']) == [['a', 'a'], ['b']]
def test_case_sensitive(): assert f(['Ab', 'bA']) == [['Ab', 'bA']]
def test_two_groups(): assert f(['ba', 'ab', 'cd']) == [['ab', 'ba'], ['cd']]
def test_bad_item():
    with pytest.raises(ValueError) as e: f([1])
    assert str(e.value) == 'bad item'
