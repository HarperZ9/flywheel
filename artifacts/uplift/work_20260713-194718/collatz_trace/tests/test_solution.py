import pytest
from solution import collatz_trace as f
def test_one(): assert f(1, 0) == [1]
def test_two(): assert f(2, 1) == [2, 1]
def test_six(): assert f(6, 100) == [6, 3, 10, 5, 16, 8, 4, 2, 1]
def test_exact_budget(): assert f(6, 8) == [6, 3, 10, 5, 16, 8, 4, 2, 1]
def test_budget_short():
    with pytest.raises(RuntimeError) as e: f(6, 7)
    assert str(e.value) == 'limit exceeded'
def test_zero_budget():
    with pytest.raises(RuntimeError) as e: f(2, 0)
    assert str(e.value) == 'limit exceeded'
def test_seven(): assert f(7, 16) == [7, 22, 11, 34, 17, 52, 26, 13, 40, 20, 10, 5, 16, 8, 4, 2, 1]
def test_seven_short():
    with pytest.raises(RuntimeError): f(7, 15)
def test_bad_start_zero():
    with pytest.raises(ValueError) as e: f(0, 5)
    assert str(e.value) == 'bad start'
def test_bad_start_bool():
    with pytest.raises(ValueError) as e: f(True, 5)
    assert str(e.value) == 'bad start'
def test_bad_start_float():
    with pytest.raises(ValueError) as e: f(1.0, 5)
    assert str(e.value) == 'bad start'
def test_bad_limit():
    with pytest.raises(ValueError) as e: f(5, -1)
    assert str(e.value) == 'bad limit'
def test_bad_limit_bool():
    with pytest.raises(ValueError) as e: f(5, True)
    assert str(e.value) == 'bad limit'
def test_start_before_limit():
    with pytest.raises(ValueError) as e: f(0, -1)
    assert str(e.value) == 'bad start'
