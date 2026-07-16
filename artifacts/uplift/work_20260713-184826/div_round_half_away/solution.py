def div_round_half_away(num: int, den: int) -> int:
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError("Both arguments must be integers.")
    if isinstance(num, bool) or isinstance(den, bool):
        raise ValueError("Arguments must not be bools.")
    if den == 0:
        raise ValueError("Denominator cannot be zero.")
    
    sign = -1 if (num < 0) ^ (den < 0) else 1
    num = abs(num)
    den = abs(den)
    
    quotient, remainder = divmod(num, den)
    if remainder == den // 2:
        rounded_quotient = quotient + sign * (quotient % 2 != 0)
    elif remainder > den // 2:
        rounded_quotient = quotient + sign
    else:
        rounded_quotient = quotient
    
    return sign * rounded_quotient
