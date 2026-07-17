def isbn10_check(s):
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError('bad isbn')
    
    for i in range(9):
        if s[i] < '0' or s[i] > '9':
            raise ValueError('bad isbn')

    if any(c == 'X' and i != 9 for i, c in enumerate(s)):
        raise ValueError('bad isbn')

    if any((c not in '0123456789Xx') and c != s[9] for i, c in enumerate(s[:9])):
        raise ValueError('bad isbn')
    
    total = sum(int(c) * (i + 1) for i, c in enumerate(s)) % 11

    return total == 0
