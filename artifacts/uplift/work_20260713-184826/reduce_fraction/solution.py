from math import gcd

def reduce_fraction(num, den):
    if not isinstance(num, int) or not isinstance(den, int) or isinstance(num, bool) or isinstance(den, bool):
        raise ValueError('bad arg')
    if den == 0:
        raise ValueError('div by zero')
    
    sign = -1 if (num < 0) ^ (den < 0) else 1
    num, den = abs(num), abs(den)
    common_divisor = gcd(num, den)
    reduced_num = num // common_divisor
    reduced_den = den // common_divisor
    
    return (sign * reduced_num, reduced_den)
