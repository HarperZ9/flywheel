def reverse_bits(n, width):
    if not isinstance(n, int) or not isinstance(width, int):
        raise ValueError('bad arg')
    if width < 1 or n < 0:
        raise ValueError('bad arg')
    max_n = (1 << width)
    if n >= max_n:
        raise ValueError('overflow')
    rev = 0
    for _ in range(width):
        rev <<= 1
        rev |= n & 1
        n >>= 1
    return rev
