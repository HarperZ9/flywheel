def diff_ops(a, b):
    if not isinstance(a, list) or not isinstance(b, list):
        raise ValueError("bad input")
    if any(not isinstance(x, str) for x in a + b):
        raise ValueError("bad input")
    if not a and not b:
        return []
    out = []
    ia = ib = 0
    while ia < len(a) or ib < len(b):
        equal = False
        try:
            while a[ia] == b[ib]:
                ia += 1; ib += 1; equal = True
        except IndexError: pass
        if equal:
            out.append(('equal', [a[ia-1]]))
        else:
            if ia < len(a):
                out.append(('delete', [a[ia]])); ia += 1
                continue
            if ib < len(b):
                out.append(('insert', [b[ib]])); ib += 1; continue
    return [(t, list(g)) for t, g in itertools.groupby([x[0] for x in out], lambda item: item[0])]
