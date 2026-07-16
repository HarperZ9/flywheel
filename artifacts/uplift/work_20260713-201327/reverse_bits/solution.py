def reverse_bits(n: int, width: int) -> int:
    # Ensure n is within the valid range (0 <= n < 2**width)
    if not isinstance(n, int) or not isinstance(width, int) or not (0 <= n <= 2 ** width - 1):
        raise ValueError("bad arg")
    
    # Calculate the number of bits in the value to be reversed
    bit_count = 1 << width
    
    def reverse_bits_helper(value: int, offset: int):
        mask = 2 ** offset
        return (value & mask) | ((value >> offset) & ~mask)
    
    result = 0
    for i in range(width):
        n_bit_index = (n >> i) & bit_count - width + 1
        low_bits = reverse_bits_helper(n, n_bit_index)
        
        if i < width - 1:
            high_bits = reverse_bits_helper(n, i + 1)
            result = reverse_bits_helper(result, high_bits) | low_bits
    
    return result
