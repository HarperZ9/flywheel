def percent_decode(s: str) -> str:
    if not isinstance(s, str):
        raise ValueError('bad input')
    
    decoded_str = ""
    i = 0
    
    while i < len(s):
        if s[i] == '%':
            if i + 3 > len(s):
                raise ValueError('bad escape')
            
            # Extract the percent-encoded byte
            hex_digit1 = s[i+1]
            hex_digit2 = s[i+2]
            
            # Check if characters are valid hexadecimal digits
            if not (hex_digit1 >= '0' and hex_digit1 <= '9' or 
                    hex_digit1 >= 'a' and hex_digit1 <= 'f' or 
                    hex_digit1 >= 'A' and hex_digit1 <= 'F'):
                raise ValueError('bad escape')
            
            # Convert the hexadecimal digits to an integer
            byte_value = int(f"{hex_digit1}{hex_digit2}", 16)
            
            if byte_value > 127:
                raise ValueError('non-ascii byte')
            
            decoded_str += chr(byte_value)
            i += 3
        elif s[i] == '+':
            decoded_str += ' '
            i += 1
        else:
            decoded_str += s[i]
            i += 1
    
    return decoded_str
