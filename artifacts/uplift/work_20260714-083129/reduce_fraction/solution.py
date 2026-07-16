def reduce_fraction(num: int, den: int) -> Tuple[int, int]:
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError('bad arg')
    if den == 0:
        raise ValueError('div by zero')
    
    # Ensure the denominator is positive
    num = abs(num)
    den = abs(den)
    
    greatest_common_divisor = gcd(num, den)
    return (num // greatest_common_divisor, den // greatest_common_divisor)

# Helper function to calculate GCD
from math import gcd

# The function definition ends here.
