from solution import count_vowels
def test_lower():
    assert count_vowels('hello')==2
def test_upper():
    assert count_vowels('HELLO')==2
def test_none():
    assert count_vowels('sky')==0
def test_empty():
    assert count_vowels('')==0
