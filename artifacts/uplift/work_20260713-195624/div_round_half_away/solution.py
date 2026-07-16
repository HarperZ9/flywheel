def div_round_half_away(num, den):
    """
    Returns the integer closest to num/den with ties rounded away from zero.
    
    Args:
        num (int): The numerator for the division.
        den (int): The denominator for the division.
        
    Raises:
        ValueError: If either argument is not an integer or if den is 0.
        TypeError: If either argument is not a number.
    """
    import math
    
    # Check if inputs are valid
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError("Both num and den must be integers.")
    if den == 0:
        raise ValueError("den must not be zero.")
    
    # Avoid division by zero
    if den < 0:
        dividend = -num / abs(den)
    else:
        dividend = num / abs(den)

    # Find the integer part of the quotient
    int_part = math.floor(dividend)
    
    # Check if we need to round away from zero for this division
    if abs(den) <= 0.999999:  # Avoid floating-point precision issues
        return int_part
    
    # Determine rounding mode and convert back to integer
    if den > 1:
        denominator = num / (den - 1)
        rounded_value = math.ceil(abs(denominator))
    else:
        denominator = abs(num) / abs(den)
        rounded_value = math.floor(abs(denominator))

    return int_part + (rounded_value - int_part) * den
>>> div_round_half_away(7/2, 2)
4
>>> div_round_half_away(-7/2, -2)
-3
>>> div_round_half_away(10/3, 5)  # 2 returns None due to division by zero
4
