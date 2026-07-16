from solution import rotate as f
def test_empty():
    assert f([]) == []
def test_one():
    assert f([[7]]) == [[7]]
def test_two():
    assert f([[1,2],[3,4]]) == [[3,1],[4,2]]
def test_three():
    assert f([[1,2,3],[4,5,6],[7,8,9]]) == [[7,4,1],[8,5,2],[9,6,3]]
def test_in_place():
    m=[[1,2],[3,4]]
    assert f(m) is m
