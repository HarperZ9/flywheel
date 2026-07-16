def reduce_fraction(num: int, den: int) -> tuple:
    if type(num) != int or type(den) != int:
        raise ValueError('bad arg')
    if den == 0:
        raise ValueError('div by zero')

    # Ensure denominator is positive
    sign = -1 if num < 0 else 1
    
    abs_num, abs_den = abs(num), abs(den)
    
    gcd = math.gcd(abs_num, abs_den)

    reduced_numerator = sign * (abs_num // gcd)
    reduced_denominator = abs_den // gcd

    return (reduced_numerator, reduced_denominator)
