def reverse_bits(n: int, width: int) -> int:
    if not isinstance(n, int) or not isinstance(width, int):
        raise ValueError('bad arg')
    if width < 1 or n < 0:
        raise ValueError('bad arg')
    max_n = (1 << width)
    if n >= max_n:
        raise ValueError('overflow')
    result: int = 0
    for _ in range(width):
        result <<= 1
        result |= n & 1
        n >>= 1
    return result
