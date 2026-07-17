import pytest
from solution import josephus as f
def test_single():
    assert f(1, 3) == 0
def test_k1():
    assert f(5, 1) == 4
def test_classic():
    assert f(7, 3) == 3
def test_two():
    assert f(2, 2) == 0
def test_bad_n():
    with pytest.raises(ValueError):
        f(0, 1)
def test_bad_k():
    with pytest.raises(ValueError):
        f(3, 0)
