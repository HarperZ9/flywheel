def round_half_even(num, den):
    if not isinstance(num, int) or not isinstance(den, int):
        raise ValueError('bad arg')
    if not den:
        raise ValueError('div by zero')
    q = num // den
    r = abs(num - q * den)
    half_den = (abs(den) + 1) // 2
    if r < half_den:
        return q
    if r > half_den:
        return q + (1 if (q >= 0) == (den > 0) else -1)
    if abs(q + (1 if (q >= 0) == (den > 0) else -1)) % 2 == 0:
        return q + (1 if (q >= 0) == (den > 0) else -1)
    return q
