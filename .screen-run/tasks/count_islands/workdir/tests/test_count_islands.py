from solution import count_islands as f
def test_empty():
    assert f([]) == 0
def test_none():
    assert f([[0,0],[0,0]]) == 0
def test_one_big():
    assert f([[1,1],[1,1]]) == 1
def test_diagonal_not_connected():
    assert f([[1,0],[0,1]]) == 2
def test_classic():
    assert f([[1,1,0,0],[1,0,0,1],[0,0,1,1]]) == 2
def test_no_mutation():
    g = [[1,0],[0,1]]
    f(g)
    assert g == [[1,0],[0,1]]
