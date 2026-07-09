from solution import max_of_three
def test_basic():
    assert max_of_three(1,2,3)==3
def test_neg():
    assert max_of_three(-5,-1,-3)==-1
def test_tie():
    assert max_of_three(4,4,2)==4
