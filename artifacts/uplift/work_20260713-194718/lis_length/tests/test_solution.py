from solution import lis_length as f
def test_empty():
    assert f([]) == 0
def test_classic():
    assert f([10,9,2,5,3,7,101,18]) == 4
def test_all_same():
    assert f([7,7,7]) == 1
def test_decreasing():
    assert f([5,4,3,2,1]) == 1
def test_increasing():
    assert f([1,2,3,4]) == 4
def test_dup_no_extend():
    assert f([1,2,2,3]) == 3
