def parse_a1(ref):
    if not isinstance(ref, str) or len(ref) == 0:
        raise ValueError('bad ref')
    
    row_str, col_str = ref[:-len(ref.split('.')[0])] if '.' in ref else ref
    if any(c.isdigit() for c in col_str + row_str):
        raise ValueError('bad ref')
    
    if not all(c.isupper() for c in col_str) or not col_str[0].isalpha():
        raise ValueError('bad ref')
    
    col_value = 0
    for char in reversed(col_str):
        col_value += (ord(char.upper()) - ord('A') + 1) * (26 ** len(reversed(col_str)))
    
    row_value = int(row_str)
    
    return (row_value, col_value)
