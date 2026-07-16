import pytest
from solution import reserve_trace as f
def test_basic():
    assert f({'w': 5}, [('reserve', 'w', 2)]) == [('w', 2)]
def test_accumulate_and_sort():
    assert f({'b': 4, 'a': 4}, [('reserve', 'b', 1), ('reserve', 'a', 2), ('reserve', 'b', 1)]) == [('a', 2), ('b', 2)]
def test_cancel_to_zero_excluded():
    assert f({'w': 5}, [('reserve', 'w', 3), ('cancel', 'w', 3)]) == []
def test_reserve_exactly_available():
    assert f({'w': 5}, [('reserve', 'w', 5)]) == [('w', 5)]
def test_no_ops():
    assert f({'w': 1}, []) == []
def test_not_enough_message():
    with pytest.raises(ValueError) as e:
        f({'widget': 3}, [('reserve', 'widget', 2), ('reserve', 'widget', 2)])
    assert str(e.value) == 'not enough widget'
def test_over_cancel():
    with pytest.raises(ValueError) as e:
        f({'w': 5}, [('reserve', 'w', 1), ('cancel', 'w', 2)])
    assert str(e.value) == 'over-cancel'
def test_unknown_item():
    with pytest.raises(ValueError) as e: f({'w': 1}, [('reserve', 'x', 1)])
    assert str(e.value) == 'unknown item'
def test_bad_qty_zero():
    with pytest.raises(ValueError) as e: f({'w': 1}, [('reserve', 'w', 0)])
    assert str(e.value) == 'bad qty'
def test_bad_qty_bool():
    with pytest.raises(ValueError): f({'w': 1}, [('reserve', 'w', True)])
def test_bad_op():
    with pytest.raises(ValueError) as e: f({'w': 1}, [('reserve', 'w')])
    assert str(e.value) == 'bad op'
def test_bad_stock_bool_value():
    with pytest.raises(ValueError) as e: f({'w': True}, [])
    assert str(e.value) == 'bad stock'
def test_bad_stock_negative():
    with pytest.raises(ValueError): f({'w': -1}, [])
def test_no_mutation():
    s = {'w': 5}
    f(s, [('reserve', 'w', 2)])
    assert s == {'w': 5}
