def percent_decode(s):
    if not isinstance(s, str):
        raise ValueError('bad input')
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '%':
            if i + 2 >= n or not (s[i+1] in '0123456789abcdefABCDEF' and s[i+2] in '0123456789abcdefABCDEF'):
                raise ValueError('bad escape')
            b = int(s[i+1:i+3], 16)
            if b >= 128:
                raise ValueError('non-ascii byte')
            out.append(chr(b))
            i += 3
        elif c == '+':
            out.append('+')
            i += 1
        else:
            out.append(c)
            i += 1
    return ''.join(out)
