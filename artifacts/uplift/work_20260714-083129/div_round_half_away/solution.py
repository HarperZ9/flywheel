def div_round_half_away(num: int, den: int) -> int:
    if type(num) != int or type(den) != int:
        raise ValueError("Both arguments must be ints.")
    if num == 0 and den == 0:
        raise ValueError("Denominator cannot be zero when numerator is also zero.")
    if den == 0:
        raise ValueError("Cannot divide by zero.")
    
    result = (num // den) * den
    remainder = num % den
    
    # Check for the case where we need to round away from zero.
    if remainder > abs(den) / 2 or (remainder == abs(den) / 2 and (num < 0 and den > 0) or (num > 0 and den < 0)):
        result += 1
    
    return -result if num < 0 else result
