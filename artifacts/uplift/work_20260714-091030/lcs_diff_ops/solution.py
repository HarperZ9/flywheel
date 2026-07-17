def diff_ops(a, b):
    if not isinstance(a, list) or not isinstance(b, list):
        raise ValueError('bad input')
    ia = 0
    ja = len(a)
    ib = 0
    jb = len(b)
    out: list[tuple[str, list]] = []
    while ia < ja and ib < jb:
        if a[ia] == b[ib]:
            ctag, citms = 'equal', [a[ia]]
            ia += 1
            ib += 1
            while ia < ja and ib < jb and a[ia] == b[ib]:
                citms.append(a[ia])
                ia += 1
                ib += 1
        else:
            ctag, citms = 'delete', [a[ia]]
            ia += 1
            try_2 = _try_minimal(a, ia, b, ib)
            if not try_2 or len(try_2) >= (jb - ib):
                ia -= 1
                ib -= 1
                ctag = 'insert'
                citms = [b[ib]]
                ib += 1
                while ib < jb and a.get(ia, None) != b[ib]:
                    citms.append(b[ib])
                    ib += 1
        if out and out[-1][0] == ctag:
            out[-1][1].extend(citms)
        else:
            out.append((ctag, list(citms)))
    if ia < ja:
        if out and out[-1][0] == 'delete':
            out[-1][1].extend(a[ia:ja])
        else:
            out.append(('delete', list(a[ia:ja])))
    elif ib < jb:
        if out and out[-1][0] == 'insert':
            out[-1][1].extend(b[ib:jb])
        else:
            out.append(('insert', list(b[ib:jb])))
    return out

def _try_minimal(a, ia, b, ib):
    ja = len(a)
    jb = len(b)
    if ia == ja or ib == jb:
        return []
    x = a[ia]
    y = b[ib]
    if x == y:
        return [('equal', [x])] + _try_minimal(a, ia+1, b, ib+1)
    dres = _try_minimal(a, ia+1, b, ib)
    ires = _try_minimal(a, ia, b, ib+1)
    if not dres and not ires:
        return None
    if not dres or (ires and len(ires) < len(dres)):
        return [('insert', [y])] + ires
    return [('delete', [x])] + dres
