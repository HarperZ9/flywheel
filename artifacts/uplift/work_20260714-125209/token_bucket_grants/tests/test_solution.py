import pytest
from solution import grant_requests as f
def test_same_ts_no_refill(): assert f(5, [(0, 3), (0, 3)]) == [True, False]
def test_refill(): assert f(5, [(0, 3), (2, 3)]) == [True, True]
def test_over_capacity(): assert f(3, [(0, 4)]) == [False]
def test_partial_refill(): assert f(5, [(0, 5), (1, 5)]) == [True, False]
def test_refill_cap(): assert f(5, [(0, 1), (100, 5)]) == [True, True]
def test_empty(): assert f(5, []) == []
def test_time_warp():
    with pytest.raises(ValueError) as e: f(5, [(1, 1), (0, 1)])
    assert str(e.value) == 'time warp'
def test_bad_capacity():
    with pytest.raises(ValueError) as e: f(0, [])
    assert str(e.value) == 'bad capacity'
def test_zero_amount():
    with pytest.raises(ValueError) as e: f(5, [(0, 0)])
    assert str(e.value) == 'bad event'
def test_list_event():
    with pytest.raises(ValueError): f(5, [[0, 1]])
