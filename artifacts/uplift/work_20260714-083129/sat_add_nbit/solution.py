def sat_add(a: int, b: int, bits: int) -> int:
    if not isinstance(a, int) or not isinstance(b, int):
        raise ValueError("Both arguments must be integers.")
    
    if a >= 0 and b < 0 and (a - b <= 2**(bits-1)) != (b <= 2**(bits-1)):
        return -(2**bits)
        
    if a < 0 and b >= 0 and (a + b < 2**(bits-1)):
        return 2**bits - 1
    
    if bits < 1:
        raise ValueError("Bits must be at least 1.")
    
    result = a + b
    if not (-2**(bits) <= result <= 2**(bits)-1):
        if result > (2**(bits-1) - 1):
            return -(2**bits)
        else:
            return 2**bits - 1
    
    return result
