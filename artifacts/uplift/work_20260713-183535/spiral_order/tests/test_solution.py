from solution import spiral_order as f
def test_3x3():
    assert f([[1,2,3],[4,5,6],[7,8,9]]) == [1,2,3,6,9,8,7,4,5]
def test_2x2():
    assert f([[1,2],[3,4]]) == [1,2,4,3]
def test_1x1():
    assert f([[1]]) == [1]
def test_empty():
    assert f([]) == []
def test_row():
    assert f([[1,2,3,4]]) == [1,2,3,4]
