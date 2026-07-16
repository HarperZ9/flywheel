def isbn10_check(s):
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError('bad isbn')
    try:
        for i in range(9):
            int(s[i])
        last = s[9]
        if last == 'X':
            last_val = 10
        else:
            last_val = int(last)
        total = sum(int(s[i]) * (10 - i) for i in range(9)) + last_val
    except ValueError:
        raise ValueError('bad isbn')
    return total % 11 == 0
