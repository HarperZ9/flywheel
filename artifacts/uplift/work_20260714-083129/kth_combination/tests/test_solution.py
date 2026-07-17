import pytest
from solution import kth_combination as f
def test_first(): assert f(4, 2, 0) == [0, 1]
def test_middle(): assert f(4, 2, 3) == [1, 2]
def test_last(): assert f(4, 2, 5) == [2, 3]
def test_five_three(): assert f(5, 3, 6) == [1, 2, 3]
def test_five_three_last(): assert f(5, 3, 9) == [2, 3, 4]
def test_k_zero(): assert f(3, 0, 0) == []
def test_k_equals_n(): assert f(3, 3, 0) == [0, 1, 2]
def test_n_zero(): assert f(0, 0, 0) == []
def test_bad_n():
    with pytest.raises(ValueError) as e: f(-1, 0, 0)
    assert str(e.value) == 'bad n'
def test_bool_n():
    with pytest.raises(ValueError) as e: f(True, 1, 0)
    assert str(e.value) == 'bad n'
def test_bad_k():
    with pytest.raises(ValueError) as e: f(3, 4, 0)
    assert str(e.value) == 'bad k'
def test_bool_k():
    with pytest.raises(ValueError) as e: f(2, True, 0)
    assert str(e.value) == 'bad k'
def test_bad_rank_high():
    with pytest.raises(ValueError) as e: f(4, 2, 6)
    assert str(e.value) == 'bad rank'
def test_bad_rank_neg():
    with pytest.raises(ValueError) as e: f(4, 2, -1)
    assert str(e.value) == 'bad rank'
def test_k_zero_rank_one():
    with pytest.raises(ValueError) as e: f(3, 0, 1)
    assert str(e.value) == 'bad rank'
