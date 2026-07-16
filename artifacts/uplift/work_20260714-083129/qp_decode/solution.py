def qp_decode(s):
    if not isinstance(s, str):
        raise ValueError('bad input')
    
    result = []
    i = 0
    
    while i < len(s):
        if s[i] == '=':
            j = i + 1
            while j < len(s) and s[j].isalnum():
                j += 1
            
            if j - i == 3:  # Check for two hex digits followed by equals sign (soft line break)
                result.append('\n')
                i = j + 1
                continue
            
            try:
                decoded_char = chr(int(s[i+1:j], 16))
            except ValueError:
                raise ValueError('bad escape') from None

            result.append(decoded_char)
            i = j
        elif s[i] != '\n':
            # Non-equal, non-soft-line-break characters pass through unchanged.
            result.append(s[i])
        
        i += 1
    
    return ''.join(result)
