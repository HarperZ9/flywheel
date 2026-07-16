import pytest
from solution import bank_ledger as f
def test_basic():
    assert f([('deposit', 100), ('withdraw', 30), ('deposit', 5)]) == [100, 70, 75]
def test_empty():
    assert f([]) == []
def test_withdraw_all():
    assert f([('deposit', 10), ('withdraw', 10)]) == [10, 0]
def test_insufficient_message():
    with pytest.raises(ValueError) as e:
        f([('deposit', 30), ('withdraw', 50)])
    assert str(e.value) == 'insufficient funds: need 50 have 30'
def test_insufficient_zero():
    with pytest.raises(ValueError) as e:
        f([('withdraw', 1)])
    assert str(e.value) == 'insufficient funds: need 1 have 0'
def test_bad_amount_zero():
    with pytest.raises(ValueError) as e: f([('deposit', 0)])
    assert str(e.value) == 'bad amount'
def test_bad_amount_bool():
    with pytest.raises(ValueError): f([('deposit', True)])
def test_bad_amount_negative():
    with pytest.raises(ValueError): f([('withdraw', -5)])
def test_bad_op_shape():
    with pytest.raises(ValueError) as e: f([('deposit',)])
    assert str(e.value) == 'bad op'
def test_bad_op_kind():
    with pytest.raises(ValueError): f([('transfer', 5)])
