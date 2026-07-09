from solution import flatten_one
def test_basic():
    assert flatten_one([1,[2,3],4])==[1,2,3,4]
def test_nested_stays():
    assert flatten_one([[1,[2]]])==[1,[2]]
def test_empty():
    assert flatten_one([])==[]
def test_no_lists():
    assert flatten_one([1,2,3])==[1,2,3]
