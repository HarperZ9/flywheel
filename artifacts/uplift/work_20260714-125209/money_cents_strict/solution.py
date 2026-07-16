def parse_money(s):
    if not s:
        raise ValueError('bad amount')
    if s == '0':
        return 0
    negative = False
    if s[0] == '-':
        negative = True
        s = s[1:]
    elif s[0] == '+':
        raise ValueError('bad amount')
    parts = s.rsplit('.', 1)
    if len(parts) > 2:
        raise ValueError('bad amount')
    integer_part, *decimal_part = parts
    if decimal_part:
        dp = ''.join(decimal_part)
        if not (dp.isdigit() and len(dp) == 2):
            raise ValueError('bad amount')
        cents = int(dp)
    else:
        cents = 0
    if ',' in integer_part:
        groups = integer_part.split(',')
        first, *rest = groups
        if not (first and first[0] != '0' and first.isdigit()):
            raise ValueError('bad amount')
        for g in rest:
            if len(g) != 3 or not g.isdigit():
                raise ValueError('bad amount')
    elif integer_part:
        if (integer_part[0] == '0' and len(integer_part) > 1) or not integer_part.isdigit():
            raise ValueError('bad amount')
    else:
        raise ValueError('bad amount')
    dollars = int(integer_part.replace(',', ''))
    return -(dollars * 100 + cents) if negative else (dollars * 100 + cents)
