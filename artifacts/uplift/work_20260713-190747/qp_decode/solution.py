def qp_decode(s):
    if not isinstance(s, str):
        raise ValueError('bad input')
    
    output = []
    i = 0
    
    while i < len(s):
        c = s[i]
        
        if c == '=':
            i += 1
            if i == len(s):
                raise ValueError('bad escape')
            
            hex_digit1 = s[i]
            i += 1
            if i == len(s) or not (hex_digit1.isdigit() or 'A' <= hex_digit1.upper() <= 'F'):
                raise ValueError('bad escape')
            
            if i < len(s):
                hex_digit2 = s[i]
                if hex_digit2.isdigit() or 'A' <= hex_digit2.upper() <= 'F':
                    try:
                        byte_value = int(f'{hex_digit1}{hex_digit2}', 16)
                        output.append(chr(byte_value))
                        continue
                    except ValueError:
                        raise ValueError('bad escape')
            
            if i < len(s) and (s[i] == '\r' or s[i] == '\n'):
                # Soft line break: skip the '=' and the CR/LF
                i += 1
                if i < len(s) and s[i] == '\n':
                    i += 1
        
        output.append(c)
        i += 1
    
    return ''.join(output)
