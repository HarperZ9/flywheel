def sat_add(a, b, bits):
    if not isinstance(bits, int) or isinstance(bits, bool) or bits < 1:
        raise ValueError("bits must be a positive integer")
    lo = -(2 ** (bits - 1))
    hi = 2 ** (bits - 1) - 1
    for v in (a, b):
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("operands must be integers")
        if not lo <= v <= hi:
            raise ValueError(f"operand {v} out of range for {bits}-bit twos-complement")
    s = a + b
    if s > hi:
        return hi
    if s < lo:
        return lo
    return s
