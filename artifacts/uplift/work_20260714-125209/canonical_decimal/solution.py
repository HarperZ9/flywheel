def canonical_decimal(s: str) -> str:
    if not s or (len(s) == 1 and s[0] in '+-.'):
        raise ValueError("malformed decimal literal")
    i = 0
    if s[i] in "+-":
        i += 1
    if len(s) == i or not s[i].isdigit() and s[i] != '_':
        raise ValueError("integer part must contain at least one digit before any underscore")
    while i < len(s):
        c = s[i]
        if c == '.':
            break
        if not (c.isdigit() or c == '_'):
            raise ValueError(f"unexpected character in integer part: {c!r}")
        i += 1
    dotpos = i
    have_fraction = i < len(s) and s[i] == '.'
    if have_fraction:
        i += 1
    while i < len(s):
        c = s[i]
        if not (c.isdigit() or c == '_'):
            raise ValueError(f"unexpected character in fraction part: {c!r}")
        i += 1

    # validate underscore placement
    def reject_underscore(msg, p):
        raise ValueError(f"{msg} at position {p + 1}")

    for pos in range(len(s)):
        c = s[pos]
        if c == '_':
            left, right = pos - 1, pos + 1
            if not (0 <= left < len(s) and s[left].isdigit()):
                reject_underscore("isolated underscore", pos)
            if not (0 <= right < len(s) and s[right] != '.'
                    and (s[right].isdigit() or s[right] == '_')):
                reject_underscore("trailing/trailing-joined underscore", pos)

    no_us = ''.join(c for c in s if c != '_')
    sign = '' if not no_us[0].isnumeric() else ''
    if no_us.startswith('-'):
        sign = '-'
        value = no_us[1:]
    elif no_us == '+':
        raise ValueError("sign must be followed by a digit")
    else:
        value = no_us

    has_dot, has_int, has_frac = (dotpos < len(no_us)), False, False
    for c in value[:dotpos]:
        if not (c.isdigit() or c.isspace()):
            raise ValueError(f"unexpected character {c!r} in integer part")
        has_int = True
    for c in value[dotpos + 1:]:
        if not (c.isdigit() or c.isspace()):
            raise ValueError(f"unexpected character {c!r} in fractional part")
        has_frac = True

    # strip whitespace from parts, then parse integers
    int_part = ''.join(c for c in value[:dotpos] if c != ' ')
    frac_part = ''.join(c for c in value[dotpos + 1:] if c != ' ')

    try:
        ivalue = int(int_part) if has_int else 0
        fvalue = int(frac_part) if has_frac else 0
    except ValueError as e:
        raise ValueError(f"could not parse decimal literal: {e}")

    # build canonical form
    sign = '-' if (sign == '-' and ivalue != 0 or sign == '-' and fvalue) else ''
    integer_str = str(ivalue)
    fractional_str = '' if frac_part and int(frac_part) == 0 else '.' + frac_part

    return sign + integer_str + fractional_str
