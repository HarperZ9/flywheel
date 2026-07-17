def sat_add(a, b, bits):
    if not all(isinstance(x, int) for x in [a, b]) or isinstance(bits, bool):
        raise ValueError("All arguments must be integers and not bools.")
    if not isinstance(bits, int) or bits < 1:
        raise ValueError("The 'bits' argument must be an integer greater than or equal to 1.")
    
    min_val = -(2 ** (bits - 1))
    max_val = 2 ** (bits - 1) - 1
    
    if a < min_val or a > max_val or b < min_val or b > max_val:
        raise ValueError("Inputs must be within the representable range for 'bits'.")
    
    result = a + b
    return min(max(result, min_val), max_val)
