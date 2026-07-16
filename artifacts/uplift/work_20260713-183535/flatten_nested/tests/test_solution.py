from solution import flatten_nested as f
def test_empty():
    assert f([]) == []
def test_flat():
    assert f([1,2,3]) == [1,2,3]
def test_deep():
    assert f([1,[2,[3,[4]]]]) == [1,2,3,4]
def test_mixed():
    assert f([[],[1],[2,[3]]]) == [1,2,3]
