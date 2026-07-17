import pytest
from solution import ring_buffer as f
def test_overwrite():
    assert f(2, [('write', 1), ('write', 2), ('write', 3), ('read',), ('read',)]) == [None, None, 1, 2, 3]
def test_peek():
    assert f(3, [('write', 7), ('peek',), ('read',)]) == [None, 7, 7]
def test_capacity_one():
    assert f(1, [('write', 1), ('write', 2), ('read',)]) == [None, 1, 2]
def test_fifo_order():
    assert f(3, [('write', 1), ('write', 2), ('read',), ('write', 3), ('read',), ('read',)]) == [None, None, 1, None, 2, 3]
def test_empty_ops():
    assert f(2, []) == []
def test_read_empty():
    with pytest.raises(ValueError) as e: f(2, [('read',)])
    assert str(e.value) == 'buffer empty'
def test_peek_empty():
    with pytest.raises(ValueError): f(2, [('peek',)])
def test_read_after_drain():
    with pytest.raises(ValueError): f(2, [('write', 1), ('read',), ('read',)])
def test_bad_capacity():
    with pytest.raises(ValueError) as e: f(0, [])
    assert str(e.value) == 'bad capacity'
def test_bad_capacity_bool():
    with pytest.raises(ValueError): f(True, [])
def test_bad_op():
    with pytest.raises(ValueError) as e: f(2, [('write',)])
    assert str(e.value) == 'bad op'
def test_bad_op_unknown():
    with pytest.raises(ValueError): f(2, [('pop',)])
