from solution import is_palindrome
def test_simple():
    assert is_palindrome('racecar')
def test_case():
    assert is_palindrome('RaceCar')
def test_punct():
    assert is_palindrome('A man, a plan, a canal: Panama')
def test_no():
    assert not is_palindrome('hello')
def test_empty():
    assert is_palindrome('')
