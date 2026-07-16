def ipv4_to_int(s):
    """
    Parses a strict dotted-quad IPv4 address and returns its 32-bit integer value.
    
    Args:
        s (str): A strictly dotted-quad IPv4 address in the format '1.2.3.4'.
        
    Returns:
        int: The 32-bit integer value of the parsed IPv4 address.
    """
    # Split the string into four parts by dots
    if '.' not in s or len(s) != 8:
        raise ValueError("Bad address")
    
    parts = s.split('.')
    
    # Validate and convert each part to an integer
    for i, part in enumerate(parts):
        if not part.isdigit():
            raise ValueError("IPv4 address must contain only digits")
        
        for char in part:
            if not (0 <= int(char) < 256):
                raise ValueError(f"Invalid IPv4 part: {part}")
    
    # Convert each part to an integer and return the sum
    return int(int(parts[0]) * 16777216 + 
              int(parts[1]) * 65536 + 
              int(parts[2]) * 256 + 
              int(parts[3]))
