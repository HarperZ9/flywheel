def div_round_half_away(num, den):
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError("both arguments must be ints")
    if den == 0:
        raise ValueError("division by zero")
    q, r = divmod(num, den)
    abs_r = abs(r)
    half = (abs(den) + 1) // 2
    if abs_r > half or (abs_r == half and (q >= 0) == (den > 0)):
        q += 1 if q >= 0 else -1
    return q
