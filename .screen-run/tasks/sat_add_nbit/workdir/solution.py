def sat_add(a, b, bits):
    def check_int(x):
        if isinstance(x, bool) or not isinstance(x, int):
            raise ValueError("expected a non-bool int")
    check_int(a)
    check_int(b)
    check_int(bits)
    if bits < 1:
        raise ValueError("bits must be >= 1")
    lo = -(1 << (bits - 1))
    hi = (1 << (bits - 1)) - 1
    if a < lo or a > hi or b < lo or b > hi:
        raise ValueError("operand out of representable range")
    s = a + b
    if s < lo:
        return lo
    if s > hi:
        return hi
    return s
