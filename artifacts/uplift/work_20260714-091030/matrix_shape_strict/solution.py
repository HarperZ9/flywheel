def matrix_shape(m):
    if not isinstance(m, list):
        raise ValueError("not a list")
    if len(m) == 0:
        raise ValueError("empty")
    first_len = None
    for r in m:
        if not isinstance(r, list):
            raise ValueError("row not list")
        if len(r) == 0:
            raise ValueError("empty row")
        this_len = len(r)
        if first_len is None:
            first_len = this_len
        elif this_len != first_len:
            raise ValueError("ragged")
        for c in r:
            if isinstance(c, bool):
                continue
            if not isinstance(c, (int, float)):
                raise ValueError("bad cell")
    return len(m), first_len
