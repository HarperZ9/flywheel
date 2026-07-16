def div_round_half_away(num: int, den: int) -> int:
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError("Both arguments must be ints and must NOT be bools.")
    if den == 0:
        raise ValueError("Second argument cannot be zero.")
    
    result = num * den >> abs(int.bit_length(den)) # Right shift to divide by a power of two
    is_negative = num < 0 != den < 0  # Determine if the result should be negative
    if (num + den) // abs(num + den) == 1: # Check if num/den is halfway between two integers
        result += is_negative
    
    return result
