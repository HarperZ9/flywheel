def canonical_decimal(s):
    def read_digits(t):
        if not t:
            return ''
        if t[0] == '_' or t[-1] == '_':
            raise ValueError("misplaced underscore")
        out = []
        prev = ''
        for ch in t:
            if ch == '_':
                if prev == '_':
                    raise ValueError("doubled underscore")
            elif '0' <= ch <= '9':
                out.append(ch)
            else:
                raise ValueError("invalid character")
            prev = ch
        return ''.join(out)

    if not s:
        raise ValueError("empty input")
    i = 0
    sign = ''
    if s[0] in '+-':
        sign = s[0]
        i = 1
    body = s[i:]
    if body.count('.') > 1:
        raise ValueError("multiple dots")
    if '.' in body:
        int_part, frac_part = body.split('.')
    else:
        int_part, frac_part = body, ''
    ip = read_digits(int_part)
    fp = read_digits(frac_part)
    if not ip and not fp:
        raise ValueError("no digits")
    ip = ip.lstrip('0') or '0'
    fp = fp.rstrip('0')
    if ip == '0' and fp == '':
        return '0'
    out = ip
    if fp:
        out += '.' + fp
    if sign == '-':
        out = '-' + out
    return out
