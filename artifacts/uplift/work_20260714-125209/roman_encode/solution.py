def to_roman(n):
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError('out of range')
    if n < 1 or n > 3999:
        raise ValueError('out of range')
    mapping = [
        (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
        (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
        (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I'),
    ]
    out = []
    for value, symbol in mapping:
        while n >= value:
            n -= value
            out.append(symbol)
    return ''.join(out)
