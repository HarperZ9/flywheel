from solution import binary_search as f
def test_found():
    assert f([1,3,5,7], 5) == 2
def test_empty():
    assert f([], 1) == -1
def test_absent():
    assert f([1,2,3], 4) == -1
def test_first():
    assert f([1,2,3,4,5], 1) == 0
def test_last():
    assert f([1,2,3,4,5], 5) == 4
def test_single():
    assert f([9], 9) == 0
