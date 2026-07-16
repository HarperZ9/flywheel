def to_roman(n):
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError('out of range')
    if n < 1 or n > 3999:
        raise ValueError('out of range')
    out = []
    for v in (1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1):
        while n >= v:
            out.append({1: 'I', 4: 'IV', 5: 'V', 9: 'IX',
                        10: 'X', 40: 'XL', 50: 'L', 90: 'XC',
                        100: 'C', 400: 'CD', 500: 'D', 900: 'CM',
                        1000: 'M'}[v])
            n -= v
    return ''.join(out)
