def gray_rank(bits):
    if not isinstance(bits, str) or len(bits) == 0:
        raise ValueError('bad code')
    for bit in bits:
        if bit not in ('0', '1'):
            raise ValueError('bad code')
    
    n = len(bits)
    value = int(bits, 2)
    rank = value ^ (value >> 1)
    return rank
