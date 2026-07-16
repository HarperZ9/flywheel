def to_base(n, base):
    if not isinstance(base, int) or isinstance(base, bool):
        raise ValueError('bad base')
    if not (2 <= base <= 36):
        raise ValueError('bad base')
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError('bad number')
    if n == 0:
        return '0'
    digits = []
    is_negative = n < 0
    n = abs(n)
    while n > 0:
        digit = n % base
        if digit < 10:
            char = chr(ord('0') + digit)
        else:
            char = chr(ord('a') + (digit - 10))
        digits.append(char)
        n //= base
    if is_negative:
        digits.append('-')
    return ''.join(reversed(digits))
