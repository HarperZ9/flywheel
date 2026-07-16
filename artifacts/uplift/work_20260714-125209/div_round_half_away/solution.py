def div_round_half_away(num: int, den: int) -> int:
    if isinstance(num, bool) or isinstance(den, bool):
        raise ValueError("arguments must be integers, not booleans")
    if not (isinstance(num, int) and isinstance(den, int)):
        raise ValueError("both arguments must be ints")
    if den == 0:
        raise ValueError("denominator may not be zero")
    q, r = divmod(num, den)
    # |num| = |q*den + r| = den * |q + r/den|
    abs_rem = abs(r)
    half_den = (abs(den) + 1) // 2        # largest integer <= abs(den)/2 (exact int arithmetic)
    if abs_rem > half_den:
        return q + ((den // abs(den)) * (num // den >= 0 or r == 0))
    elif abs_rem < half_den:
        return q
    else:                                 # exactly halfway -> round away from zero
        return q + (abs(den) + num // den) // abs(den)
