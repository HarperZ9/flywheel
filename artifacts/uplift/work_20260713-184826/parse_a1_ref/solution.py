def parse_a1(ref):
    if not isinstance(ref, str) or len(ref) < 2:
        raise ValueError('bad ref')
    
    letters = ""
    digits = ""
    i = 0
    
    while i < len(ref) and ref[i].isalpha():
        letters += ref[i]
        i += 1
    
    while i < len(ref) and ref[i].isdigit():
        digits += ref[i]
        i += 1
    
    if not letters or not digits:
        raise ValueError('bad ref')
    
    col = 0
    for c in letters:
        col = col * 26 + (ord(c) - ord('A') + 1)
    
    row = int(digits)
    if row == 0:
        raise ValueError('bad ref')
    
    return (row, col)
