def parse_a1(ref):
    if not isinstance(ref, str) or not (c := ''.join(filter(str.isupper, ref))) or \
            any(c[n] in '0-9' for n in range(len(c)-1)):
        raise ValueError('bad ref')
    if not any(d.isdigit() and d != '0' for d in filter(str.isdigit, ref[1:])):
        raise ValueError('bad ref')
    row = int(''.join(x for x in ref if x.isdigit()))
    col = 1 + sum((ord(c[i]) - ord('A')) * (26 ** i) for i in range(len(c)))
    return row, col
