from solution import second_largest
def test_basic():
    assert second_largest([3,1,4,1,5,9,2,6])==6
def test_neg():
    assert second_largest([-1,-5,-2])==-2
def test_dups():
    assert second_largest([5,5,5,3])==3
def test_one():
    assert second_largest([7]) is None
def test_empty():
    assert second_largest([]) is None
