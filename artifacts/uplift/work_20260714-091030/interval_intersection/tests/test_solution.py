from solution import interval_intersection as f
def test_empty():
    assert f([], [[1,2]]) == []
def test_disjoint():
    assert f([[1,2]], [[3,4]]) == []
def test_touching():
    assert f([[1,3]], [[3,5]]) == [[3,3]]
def test_nested():
    assert f([[1,10]], [[2,3],[5,6]]) == [[2,3],[5,6]]
def test_classic():
    assert f([[0,2],[5,10],[13,23],[24,25]], [[1,5],[8,12],[15,24],[25,26]]) == [[1,2],[5,5],[8,10],[15,23],[24,24],[25,25]]
