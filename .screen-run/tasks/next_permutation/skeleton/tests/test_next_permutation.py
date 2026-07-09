from solution import next_permutation as f
def test_empty():
    assert f([]) == []
def test_simple():
    assert f([1,2,3]) == [1,3,2]
def test_wrap():
    assert f([3,2,1]) == [1,2,3]
def test_dup():
    assert f([1,1,5]) == [1,5,1]
def test_middle():
    assert f([1,3,2]) == [2,1,3]
def test_in_place():
    m=[1,2]
    assert f(m) is m and m == [2,1]
