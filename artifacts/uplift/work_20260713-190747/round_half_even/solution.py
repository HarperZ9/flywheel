def round_half_even(num: int, den: int) -> int:
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError('bad arg')
    if den == 0:
        raise ValueError('div by zero')
    
    quotient = num / den
    
    # Handle rounding to the nearest integer using round half to even
    rounded_quotient = round(quotient * 2) / 2
    
    return int(rounded_quotient)
