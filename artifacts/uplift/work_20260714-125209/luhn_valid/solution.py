def luhn_valid(s):
    if not isinstance(s, str) or not s or any(c < '0' or c > '9' for c in s):
        raise ValueError('bad number')
    total = 0
    parity = len(s) & 1
    for i, c in enumerate(s):
        n = int(c)
        if (i & 1) == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0
