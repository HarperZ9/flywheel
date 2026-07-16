import pytest
from solution import lru_trace as f
def test_basic_eviction():
    assert f(2, [('put', 'a', 1), ('put', 'b', 2), ('put', 'c', 3), ('get', 'a'), ('get', 'b'), ('get', 'c')]) == [None, 2, 3]
def test_get_refreshes():
    assert f(2, [('put', 'a', 1), ('put', 'b', 2), ('get', 'a'), ('put', 'c', 3), ('get', 'b'), ('get', 'a'), ('get', 'c')]) == [1, None, 1, 3]
def test_put_updates_no_evict():
    assert f(2, [('put', 'a', 1), ('put', 'b', 2), ('put', 'a', 9), ('put', 'c', 3), ('get', 'a'), ('get', 'b'), ('get', 'c')]) == [9, None, 3]
def test_miss_no_recency():
    assert f(2, [('put', 'a', 1), ('put', 'b', 2), ('get', 'zz'), ('put', 'c', 3), ('get', 'a'), ('get', 'b')]) == [None, None, 2]
def test_capacity_one():
    assert f(1, [('put', 'a', 1), ('put', 'b', 2), ('get', 'a'), ('get', 'b')]) == [None, 2]
def test_empty_ops():
    assert f(3, []) == []
def test_bad_capacity_zero():
    with pytest.raises(ValueError) as e: f(0, [])
    assert str(e.value) == 'bad capacity'
def test_bad_capacity_bool():
    with pytest.raises(ValueError): f(True, [])
def test_bad_op_shape():
    with pytest.raises(ValueError) as e: f(2, [('get', 'a', 'b')])
    assert str(e.value) == 'bad op'
def test_bad_op_name():
    with pytest.raises(ValueError): f(2, [('del', 'a')])
def test_bad_op_list():
    with pytest.raises(ValueError): f(2, [['get', 'a']])
