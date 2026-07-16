import pytest
from solution import diff_ops as f
def test_replace_middle():
    assert f(['a', 'b', 'c'], ['a', 'x', 'c']) == [('equal', ['a']), ('delete', ['b']), ('insert', ['x']), ('equal', ['c'])]
def test_all_equal(): assert f(['a', 'b'], ['a', 'b']) == [('equal', ['a', 'b'])]
def test_both_empty(): assert f([], []) == []
def test_insert_only(): assert f([], ['a', 'b']) == [('insert', ['a', 'b'])]
def test_delete_only(): assert f(['a', 'b'], []) == [('delete', ['a', 'b'])]
def test_disjoint():
    assert f(['a', 'b'], ['c', 'd']) == [('delete', ['a', 'b']), ('insert', ['c', 'd'])]
def test_shift():
    assert f(['x', 'a'], ['a', 'y']) == [('delete', ['x']), ('equal', ['a']), ('insert', ['y'])]
def test_tie_prefers_delete():
    assert f(['a', 'b', 'a'], ['b', 'a', 'b']) == [('delete', ['a']), ('equal', ['b', 'a']), ('insert', ['b'])]
def test_append(): assert f(['a'], ['a', 'b']) == [('equal', ['a']), ('insert', ['b'])]
def test_prepend(): assert f(['b'], ['a', 'b']) == [('insert', ['a']), ('equal', ['b'])]
def test_bad_input_not_list():
    with pytest.raises(ValueError) as e: f('ab', [])
    assert str(e.value) == 'bad input'
def test_bad_element():
    with pytest.raises(ValueError) as e: f([1], [])
    assert str(e.value) == 'bad input'
