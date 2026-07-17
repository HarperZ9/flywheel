def parse_a1(ref: str) -> tuple:
    if not isinstance(ref, str):
        raise ValueError('bad ref')
    if not ref:
        raise ValueError('bad ref')
    
    col = 0
    row = int(ref)
    
    # Extract column part from ref
    for i, char in enumerate(reversed(ref)):
        if not 'A' <= char <= 'Z':
            raise ValueError('bad ref')
        col += (ord(char) - ord('A') + 1) * (26 ** i)
        
    return (row, col)
