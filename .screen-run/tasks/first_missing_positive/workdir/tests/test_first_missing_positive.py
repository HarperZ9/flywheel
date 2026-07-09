from solution import first_missing_positive as f
def test_empty():
    assert f([]) == 1
def test_gap():
    assert f([1,2,0]) == 3
def test_classic():
    assert f([3,4,-1,1]) == 2
def test_all_high():
    assert f([7,8,9]) == 1
def test_dups():
    assert f([1,1,2]) == 3
def test_no_mutation():
    g=[2,1]
    f(g)
    assert g == [2,1]
