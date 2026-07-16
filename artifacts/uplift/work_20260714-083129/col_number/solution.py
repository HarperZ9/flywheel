def col_number(s: str) -> int:
    if not s or not isinstance(s, str):
        raise ValueError('bad label')
    
    result = 0
    for char in s:
        if not 'A' <= char <= 'Z':
            raise ValueError('bad label')
        result *= 26
        result += ord(char) - ord('A') + 1
    return result
