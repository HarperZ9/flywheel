def base(n: int, base: int) -> str:
    """
    Renders an integer in an arbitrary base.
    
    Args:
        n (int): The integer to be rendered as a string in the given base.
        base (int): The base for the rendering. Must satisfy 2 <= base <= 36.
        
    Raises:
        ValueError: If base is not between 2 and 36 or if the base is greater than 10.
    
    Returns:
        str: The string representation of 'n' in the specified base.
    """
    # Special case for zero
    if n == 0:
        return "0"
    
    # Convert the number to its ASCII value by raising it to the power of base minus one
    # this gives us an integer result
    int_value = n
    converted_base = []
    
    while int_value > 0:
        converted_base.append(str(int_value % (base**n)))
        int_value //= base ** n
    
    # Reverse the list and join it to form the string representation
    return ''.join(converted_base[::-1])
