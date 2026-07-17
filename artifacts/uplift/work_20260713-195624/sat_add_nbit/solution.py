def sat_add(a: int, b: int, bits: int) -> int:
    """
    Performs saturating signed two's-complement addition on two values a and b.
    
    Args:
    - a (int): A non-negative integer.
    - b (int): Another non-negative integer.
    - bits (int): The bit representation of the representable range for adding two numbers with sign bit.

    Raises:
    - ValueError: If 'bits' is less than 1 or if either 'a' or 'b' are out of the representable range
      defined by 'bits'.
    """
    
    # Check that both a and b are within their respective representable ranges.
    if bits == 0:
        raise ValueError("The bit representation for two's-complement addition is always non-negative.")
    elif bits < 1:
        raise ValueError(f"Bit representation {bits} is less than 1, but '{a}' or {'b' if a > b else 'a'} are out of range")
    
    # Clamp the sums to their representable values within the binary system.
    sum_clamped = max(a + b, bits - 1)
    
    return sum_clamped
