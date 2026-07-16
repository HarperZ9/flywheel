def percent_decode(s):
    if not isinstance(s, str):
        raise ValueError('bad input')
    
    decoded = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '%':
            if i + 2 >= len(s) or not s[i+1].isdigit() and not s[i+1].islower() and not s[i+1].isupper():
                raise ValueError('bad escape')
            hex_digit1 = s[i+1]
            hex_digit2 = s[i+2]
            byte_value = int(f'{hex_digit1}{hex_digit2}', 16)
            if byte_value >= 128:
                raise ValueError('non-ascii byte')
            decoded.append(bytes([byte_value]).decode())
            i += 3
        else:
            if ch == '+':
                decoded.append(' ')
            else:
                decoded.append(ch)
            i += 1
    
    return ''.join(decoded)
