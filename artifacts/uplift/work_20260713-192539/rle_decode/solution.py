def rle_decode(s: str) -> str:
    result = ''
    i = 0
    
    while i < len(s):
        if s[i].isnumeric():
            # Count extraction logic
            j = i + 1
            while j < len(s) and s[j].isnumeric():
                j += 1
            count_str = s[i:j]
            count = int(count_str)
            
            i = j
            
            # Character extraction logic
            j = i + 1
            while j < len(s) and not s[j].isnumeric():
                j += 1
            char = s[i:j]
            
            result += char * count if count > 0 else ''
        elif s[i] != '':
            raise ValueError("Malformed input")
        
        i += 1
    
    return result
