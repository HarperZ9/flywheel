import pytest
from solution import min_stack as f
def test_trace():
    assert f([('push', 3), ('push', 1), ('min',), ('push', 2), ('min',), ('top',), ('pop',), ('min',), ('pop',), ('min',)]) == [1, 1, 2, 2, 1, 1, 3]
def test_empty_ops():
    assert f([]) == []
def test_negative():
    assert f([('push', 5), ('push', -2), ('min',), ('pop',), ('min',)]) == [-2, -2, 5]
def test_duplicate_min():
    assert f([('push', 1), ('push', 1), ('pop',), ('min',)]) == [1, 1]
def test_pop_empty():
    with pytest.raises(ValueError) as e: f([('pop',)])
    assert str(e.value) == 'empty stack'
def test_min_empty():
    with pytest.raises(ValueError) as e: f([('min',)])
    assert str(e.value) == 'empty stack'
def test_top_empty():
    with pytest.raises(ValueError): f([('top',)])
def test_push_bool():
    with pytest.raises(ValueError) as e: f([('push', True)])
    assert str(e.value) == 'bad op'
def test_push_missing_arg():
    with pytest.raises(ValueError): f([('push',)])
def test_bad_ops():
    with pytest.raises(ValueError) as e: f('nope')
    assert str(e.value) == 'bad ops'
def test_unknown_op():
    with pytest.raises(ValueError): f([('peek',)])
