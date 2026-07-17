from solution import two_sum as f
def test_basic():
    assert f([2,7,11,15], 9) == [0,1]
def test_mid():
    assert f([3,2,4], 6) == [1,2]
def test_dup():
    assert f([3,3], 6) == [0,1]
def test_none():
    assert f([1,2,3], 100) == []
def test_neg():
    assert f([-3,4,3,90], 0) == [0,2]
