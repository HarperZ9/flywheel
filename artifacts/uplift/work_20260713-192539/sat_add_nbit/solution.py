def sat_add(a, b, bits):
    if not isinstance(a, int) or not isinstance(b, int) or not isinstance(bits, int):
        raise ValueError("All arguments must be ints.")
    
    if a is True or a is False or b is True or b is False or bits is True or bits is False:
        raise ValueError("Arguments cannot be bools.")

    if bits < 1:
        raise ValueError("bits must be at least 1.")
        
    max_val = (1 << (bits - 1)) - 1
    min_val = -(1 << (bits - 1))
    
    if a > max_val or a < min_val or b > max_val or b < min_val:
        raise ValueError("Inputs must be within the representable range for bits.")
        
    return ((a + b) & ((1 << bits) - 1))
