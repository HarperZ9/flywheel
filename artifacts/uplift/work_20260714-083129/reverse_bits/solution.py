def reverse_bits(n: int, width: int) -> int:
    if not isinstance(n, int) or not isinstance(width, int):
        raise ValueError('bad arg')
    if n < 0 or width < 1:
        raise ValueError('bad arg')
    if n >= (1 << width):
        raise ValueError('overflow')

    result = 0
    for _ in range(width):
        result = (result << 1) | (n & 1)
        n >>= 1

    return result
