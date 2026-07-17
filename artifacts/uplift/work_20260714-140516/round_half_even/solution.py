def round_half_even(num: int, den: int) -> int:
    if not isinstance(num, int) or isinstance(num, bool):
        raise ValueError('bad arg')
    if not isinstance(den, int) or isinstance(den, bool):
        raise ValueError('bad arg')
    if den == 0:
        raise ValueError('div by zero')
    
    # Compute the exact fraction
    n = abs(num)
    d = abs(den)

    # Integer division and remainder
    quotient = (n // d) * ((-1, 1)[num >= 0] * (-1, 1)[den > 0])
    remainder = n % d

    # Halfway point
    half = d >> 1

    if remainder < half:
        return quotient + (1 if num < 0 <= den else -1)
    elif remainder > half:
        return quotient + (1 if num > 0 or den < 0 else -1)
    else:  # exactly halfway
        # Check if result is even
        q_abs = abs(quotient)
        if q_abs % 2 == 0:
            return quotient
        else:
            return quotient + (1 if num < 0 <= den else -1)

# Example usage:
# print(round_half_even(1, 2))  # should be 0
# print(round_half_even(3, 2))  # should be 2
# print(round_half_even(-1, 2))  # should be 0
