def col_number(s):
    if not s or not s.isupper() or len(s) == 0:
        raise ValueError('bad label')
    
    result = 0
    for char in s:
        if ord(char) < ord('A') or ord(char) > ord('Z'):
            raise ValueError('bad label')
        result = result * 26 + (ord(char) - ord('A') + 1)
    
    return result
