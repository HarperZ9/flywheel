def gray_rank(bits):
    if not isinstance(bits, str) or len(bits) == 0:
        raise ValueError('bad code')
    
    for bit in bits:
        if bit != '0' and bit != '1':
            raise ValueError('bad code')
    
    def n_bit_gray(index: int) -> str:
        return bin(index)[2:].zfill(len(bits))
    
    # Invert the gray sequence to find the original index
    inverted_gray = []
    for i in range(2**len(bits)):
        inverted_gray.append(n_bit_gray(i ^ (i >> 1)))
    
    return inverted_gray.index(bits)
