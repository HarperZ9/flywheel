def reverse_bits(n, width):
    if not isinstance(n, int) or not isinstance(width, int) or bool(n) or bool(width):
        raise ValueError('bad arg')
    if width < 1 or n < 0 or n >= 2 ** width:
        raise ValueError('bad arg')
    
    result = 0
    for _ in range(width):
        result <<= 1
        result |= n & 1
        n >>= 1
    
    return result
