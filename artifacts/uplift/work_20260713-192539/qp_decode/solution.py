def qp_decode(s: str) -> str:
    if not isinstance(s, str):
        raise ValueError('bad input')
    
    result = []
    i = 0
    
    while i < len(s):
        if s[i] == '=':
            # Check for short line break
            if (i + 2) <= len(s) and (s[i+1] in '\n\r' or s[i:i+3].upper() == 'CRLF'):
                result.append('\n')
                i += 2 if (i + 1) < len(s) and s[i+1] in '\r\n' else 3
            # Check for hex escape sequence
            elif (i + 4) <= len(s) and all(c in '0123456789ABCDEFabcdef' for c in s[i:i+4]) and s[i+3].isspace():
                result.append(chr(int(s[i:i+4], 16)))
                i += 4
            else:
                raise ValueError('bad escape')
        else:
            if s[i] != '\n':
                result.append(s[i])
        i += 1
    
    return ''.join(result)
