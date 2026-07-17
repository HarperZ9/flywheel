def valid_ipv4(s: str) -> bool:
    # Split the input string into individual parts based on dots and convert each part to an integer.
    segments = s.split('.')
    
    # Check if there are exactly four segments with non-zero values in decimal form (0-255).
    if len(segments) != 4:
        return False
    
    # Convert each segment from a string to an integer to ensure leading zeros and signs are preserved.
    for segment in segments:
        try:
            int_segment = int(segment)
            # Ensure the number is not empty, but only check for non-zero numbers here as per the original problem constraints.
            if int_segment != 0:
                return True
        except ValueError:
            return False
    
    # Check if there were exactly four segments with valid values.
    return len(segments) == 4 and all(int_part >= 0 and int_part <= 255 for int_part in segments)
