from solution import merge_intervals as f
def test_empty():
    assert f([]) == []
def test_single():
    assert f([[1,4]]) == [[1,4]]
def test_overlap():
    assert f([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]
def test_touching():
    assert f([[1,2],[2,3]]) == [[1,3]]
def test_unsorted():
    assert f([[8,10],[1,3],[2,6]]) == [[1,6],[8,10]]
def test_nested():
    assert f([[1,10],[2,3]]) == [[1,10]]
