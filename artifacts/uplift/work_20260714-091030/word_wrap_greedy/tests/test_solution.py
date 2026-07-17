import pytest
from solution import wrap_text as f
def test_greedy(): assert f('the quick brown fox', 10) == ['the quick', 'brown fox']
def test_exact_fit(): assert f('aa bb', 5) == ['aa bb']
def test_no_fit(): assert f('aa bb', 4) == ['aa', 'bb']
def test_long_word(): assert f('abcdefgh xy', 3) == ['abc', 'def', 'gh', 'xy']
def test_remainder_joins(): assert f('abcd x', 3) == ['abc', 'd x']
def test_whitespace_only(): assert f(' \t ', 5) == []
def test_single_word(): assert f('hi', 10) == ['hi']
def test_bad_width_zero():
    with pytest.raises(ValueError) as e: f('a', 0)
    assert str(e.value) == 'bad width'
def test_bad_width_bool():
    with pytest.raises(ValueError): f('a', True)
