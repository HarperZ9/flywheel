def round_half_even(num: int, den: int) -> int:
    if not isinstance(num, int) or isinstance(num, bool):
        raise ValueError('bad arg')
    if not isinstance(den, int) or isinstance(den, bool):
        raise ValueError('bad arg')
    if den == 0:
        raise ValueError('div by zero')
    
    # Compute the exact fraction value as an integer numerator of
    # (numerator / denominator), with a common factor cancelled out of
    # both. This is the precise representation.
    g = gcd(num, den)
    num //= g
    den //= g
    
    # When abs(den) == 1 it is already in integer form, so return it.
    if abs(den) == 1:
        return int(num)
    
    q, r = divmod(abs(num), abs(den))
    half_den = (abs(den) + 1) >> 1
    
    # q is the quotient toward zero; q+1 is the opposite direction.
    # Check if we are halfway between two integers. By construction
    # |r| < abs(den), so we have exactly one half-interval in each
    # direction from the integer midpoint (q, q+1).
    if r == half_den or (den > 0 and r == -half_den):
        # Halfway: round to the nearest even result.
        if q % 2 == 0:
            return int(num // den)
        else:
            return int((num + (1 if den < 0 else (-1))) // den)
    elif abs(r) > half_den:
        # Past halfway; round away from zero.
        return int((num + (1 if den < 0 else (-1))) // den)
    else:
        # Less than halfway; round toward zero.
        return int(num // den)
