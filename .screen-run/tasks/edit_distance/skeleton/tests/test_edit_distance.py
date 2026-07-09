from solution import edit_distance as f
def test_both_empty():
    assert f('', '') == 0
def test_one_empty():
    assert f('abc', '') == 3
def test_equal():
    assert f('same', 'same') == 0
def test_classic():
    assert f('horse', 'ros') == 3
def test_sub_only():
    assert f('kitten', 'sitten') == 1
def test_intention():
    assert f('intention', 'execution') == 5
