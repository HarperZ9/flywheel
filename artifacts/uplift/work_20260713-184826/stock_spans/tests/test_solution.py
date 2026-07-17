import pytest
from solution import stock_spans as f
def test_classic(): assert f([100, 80, 60, 70, 60, 75, 85]) == [1, 1, 1, 2, 1, 4, 6]
def test_empty(): assert f([]) == []
def test_single(): assert f([10]) == [1]
def test_increasing(): assert f([10, 20, 30]) == [1, 2, 3]
def test_decreasing(): assert f([30, 20, 10]) == [1, 1, 1]
def test_equal(): assert f([5, 5, 5]) == [1, 2, 3]
def test_bad_price_bool():
    with pytest.raises(ValueError) as e: f([True])
    assert str(e.value) == 'bad price'
def test_bad_price_type():
    with pytest.raises(ValueError): f(['x'])
