def parse_money(s):
    if not isinstance(s, str) or not s:
        raise ValueError('bad amount')
    if s[0] == '-':
        sign = -1
        s = s[1:]
    else:
        sign = 1
        if s[0] == '+':
            raise ValueError('bad amount')
    parts = s.rsplit('.', 1)
    if len(parts) == 2 and not parts[1]:
        # Trailing . with no fraction
        raise ValueError('bad amount')
    elif len(parts) > 2:
        raise ValueError('bad amount')
    if len(parts) == 1:
        int_part, frac = s, '00'
    else:
        int_part, frac = parts[0], parts[1]
    if not (len(frac) in {0, 2} and frac.isdigit()):
        raise ValueError('bad amount')
    if int_part == '':
        return 0
    if len(int_part) > 1 and int_part[0] == '0':
        # Leading zero on a multi-char value
        raise ValueError('bad amount')
    comma_groups = int_part.split(',')
    if ',' in int_part:
        if not all(len(g) == 3 for g in comma_groups[1:]):
            # Every group after the first must be exactly three digits with commas present
            raise ValueError('bad amount')
    else:
        if len(comma_groups[0]) > 3:
            raise ValueError('bad amount')
    try:
        total_cents = sign * (int(int_part.replace(',', '')) * 100 + int(frac))
    except ValueError:
        raise ValueError('bad amount') from None
    return total_cents
