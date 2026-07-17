def qp_decode(s):
    if not isinstance(s, str):
        raise ValueError('bad input')
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '=':
            i += 1
            if i + 2 <= n and s[i:i+2].isalnum() and all(x in '0123456789ABCDEF' for x in s[i:i+2]):
                out.append(chr(int(s[i:i+2], 16)))
                i += 2
            elif i < n and (s[i] == '\n' or (s[i] == '\r' and (i + 1 < n and s[i+1] == '\n'))):
                if s[i] == '\r':
                    i += 1
                i += 1
            else:
                raise ValueError('bad escape')
        else:
            out.append(c)
            i += 1
    return ''.join(out)
