from solution import fizzbuzz
def test_basic():
    assert fizzbuzz(5)==['1','2','Fizz','4','Buzz']
def test_fifteen():
    r = fizzbuzz(15)
    assert r[14]=='FizzBuzz' and r[2]=='Fizz' and r[4]=='Buzz'
def test_empty():
    assert fizzbuzz(0)==[]
