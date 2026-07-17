def percent_decode(s: str) -> str:
    """
    Decodes a percent-encoded ASCII string.
    
    Parameters:
    s (str): A percent encoded ASCII string to decode.
        
    Returns:
    str: The decoded ASCII string.
    """
    try:
        # Find the escape sequence
        while '%%' in s:
            i = s.index('%%')
            byte_name = s[:i]
            
            # Validate the hexadecimal digits at the begining of the name
            if not (0x31 <= byte_name <= 0x7a and len(byte_name) == 2):
                raise ValueError('bad escape')

            # Decode the hexadecimal name to get the numeric value
            number = int(byte_name, 16)
            
            # Translate the numeric value into its ASCII character
            if number >= 65:
                s = s[:i] + chr(number) + s[i+2:]
            else:
                raise ValueError('non-ascii byte')
        
        return s

    except Exception as e:
        print(f"Error decoding: {e}")
