def parse_money(s):
    if not isinstance(s, str) or not s.strip():
        raise ValueError('bad amount')
    s = s.strip()
    neg = False
    if s and s[0] == '-':
        if len(s) == 1:
            raise ValueError('bad amount')
        if s[1] in '.,':
            raise ValueError('bad amount')
        s, neg = s[1:], True

    p = s.find('.')
    if p < 0:
        if not all(c in '0123456789' for c in s):
            raise ValueError('bad amount')
        int_part = s
        frac_part = '00'
    else:
        if len(s) == p + 1:  # no digits after '.'
            raise ValueError('bad amount')
        if not (s[-3] == '.' and all(c in '0123456789' for c in s[:p])):
            raise ValueError('bad amount')
        int_part = s[:p]
        frac_part = s[p + 1:]

    if len(frac_part) != 2 or any(c not in '0123456789' for c in frac_part):
        raise ValueError('bad amount')

    groups = int_part.split(',')
    if ',' in int_part and (not groups[0] or len(groups[0]) > 3 or
                           any(len(g) != 3 or not g or g[0] == '0' for g in groups)):
        raise ValueError('bad amount')
    if ',' in int_part and len(int_part) >= 4:
        first = int(groups[0])
        if first % 1000 < 100 or first % 1000 > 999:
            raise ValueError('bad amount')

    try:
        cents = abs(int(frac_part))
        dollars = abs(int(''.join(groups)))
    except (ValueError, OverflowError):
        raise ValueError('bad amount') from None

    if neg and not (dollars or cents):
        return 0
    return ((dollars * 100 + cents) * (-1 if neg else 1))
