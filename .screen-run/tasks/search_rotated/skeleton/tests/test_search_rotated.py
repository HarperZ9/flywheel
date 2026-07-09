from solution import search_rotated as f
def test_empty():
    assert f([], 1) == -1
def test_single_hit():
    assert f([5], 5) == 0
def test_unrotated():
    assert f([1,2,3,4,5], 4) == 3
def test_rotated_hit():
    assert f([4,5,6,7,0,1,2], 0) == 4
def test_rotated_miss():
    assert f([4,5,6,7,0,1,2], 3) == -1
def test_pivot_edge():
    assert f([3,1], 1) == 1
