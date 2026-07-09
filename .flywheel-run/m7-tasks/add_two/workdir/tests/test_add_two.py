from solution import add
def test_pos():
    assert add(2,3)==5
def test_neg():
    assert add(-1,-1)==-2
def test_zero():
    assert add(0,5)==5
