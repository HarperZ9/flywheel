from solution import dedupe
def test_basic():
    assert dedupe([1,2,2,3,1])==[1,2,3]
def test_empty():
    assert dedupe([])==[]
def test_all_same():
    assert dedupe([5,5,5])==[5]
def test_strings():
    assert dedupe(['a','b','a'])==['a','b']
