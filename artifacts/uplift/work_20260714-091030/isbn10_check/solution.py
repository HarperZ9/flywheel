def isbn10_check(s):
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError('bad isbn')
    try:
        digits = [int(c) for c in s[:9]]
        last = s[9]
        if last == 'X':
            last_value = 10
        else:
            last_value = int(last)
    except (ValueError, TypeError):
        raise ValueError('bad isbn')
    total = sum(d * (10 - i) for i, d in enumerate(digits)) + last_value
    return total % 11 == 0
