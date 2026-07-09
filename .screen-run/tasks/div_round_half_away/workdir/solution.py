def div_round_half_away(num, den):
    for v in (num, den):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("expected a non-bool int")
    if den == 0:
        raise ValueError("denominator must be nonzero")
    negative = (num < 0) != (den < 0)
    n = abs(num)
    d = abs(den)
    q, r = divmod(n, d)
    if 2 * r >= d:
        q += 1
    return -q if negative else q
