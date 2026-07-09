from solution import word_break as f
def test_empty():
    assert f('', ['a']) is True
def test_simple():
    assert f('leetcode', ['leet','code']) is True
def test_reuse():
    assert f('appleapple', ['apple']) is True
def test_no():
    assert f('catsandog', ['cats','dog','sand','and','cat']) is False
def test_case():
    assert f('Ab', ['ab']) is False
def test_overlap_choice():
    assert f('aaab', ['a','aa','ab']) is True
