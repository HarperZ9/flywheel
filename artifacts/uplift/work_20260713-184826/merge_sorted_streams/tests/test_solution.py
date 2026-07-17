from solution import merge_sorted as f
def test_empty_outer():
    assert f([]) == []
def test_empty_inners():
    assert f([[], []]) == []
def test_two():
    assert f([[1,4,5],[1,3,4]]) == [1,1,3,4,4,5]
def test_singletons():
    assert f([[2],[1],[3]]) == [1,2,3]
def test_one_list():
    assert f([[1,2,3]]) == [1,2,3]
def test_interleaved():
    a = list(range(0, 100, 2)); b = list(range(1, 100, 2))
    assert f([a, b]) == list(range(100))
