import pytest
from solution import k_smallest as f
def test_basic():
    assert f([('a', 3), ('b', 1), ('c', 2)], 2) == ['b', 'c']
def test_tie_break():
    assert f([('z', 1), ('a', 1), ('m', 0)], 2) == ['m', 'a']
def test_k_zero():
    assert f([('a', 1)], 0) == []
def test_k_exceeds():
    assert f([('b', 2), ('a', 1)], 9) == ['a', 'b']
def test_empty():
    assert f([], 3) == []
def test_negative_scores():
    assert f([('a', -1), ('b', -5)], 1) == ['b']
def test_duplicate_name():
    with pytest.raises(ValueError) as e: f([('a', 1), ('a', 2)], 1)
    assert str(e.value) == 'duplicate name'
def test_bad_record_list():
    with pytest.raises(ValueError) as e: f([['a', 1]], 1)
    assert str(e.value) == 'bad record'
def test_bad_record_bool_score():
    with pytest.raises(ValueError): f([('a', True)], 1)
def test_bad_record_len():
    with pytest.raises(ValueError): f([('a', 1, 2)], 1)
def test_bad_k_bool():
    with pytest.raises(ValueError) as e: f([], True)
    assert str(e.value) == 'bad k'
def test_bad_k_negative():
    with pytest.raises(ValueError): f([], -1)
