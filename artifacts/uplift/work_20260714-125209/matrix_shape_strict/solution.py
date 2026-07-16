def matrix_shape(m):
    if not isinstance(m, list):
        raise ValueError('not a list')
    if len(m) == 0:
        raise ValueError('empty')
    first_len = None
    for r in m:
        if not isinstance(r, list):
            raise ValueError('row not list')
        if len(r) == 0:
            raise ValueError('empty row')
        if first_len is None:
            first_len = len(r)
        elif len(r) != first_len:
            raise ValueError('ragged')
        for v in r:
            if isinstance(v, bool):
                continue
            try:
                float(v)
            except (TypeError, ValueError):
                raise ValueError('bad cell')
    return len(m), first_len
