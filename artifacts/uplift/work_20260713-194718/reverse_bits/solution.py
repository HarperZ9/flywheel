def reverse_bits(n: int, width: int) -> int:
    if n < 0 or width < 1:
        raise ValueError('bad arg')
        
    max_value = (2 ** width) - 1
    if n >= max_value:
        raise ValueError('overflow')
        
    reversed_int = 0
    for _ in range(width):
        reversed_int = (reversed_int << 1) | (n & 1)
        n >>= 1
        
    return reversed_int
