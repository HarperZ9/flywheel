def ipv4_to_int(s):
    if not isinstance(s, str):
        raise ValueError('bad address')
    parts = s.split('.')
    if len(parts) != 4:
        raise ValueError('bad address')
    out = 0
    for i, p in enumerate(parts):
        if not (p == '0' or p and p[0] != '0' and p.isdigit()):
            raise ValueError('bad address')
        n = int(p)
        if n < 0 or n > 255:
            raise ValueError('bad address')
        out += n << ((3 - i) * 8)
    return out
