def transpose(m):
    if not isinstance(m, list):
        raise ValueError('bad matrix')
    if not m:
        return []
    first_len = len(m[0])
    if not all(isinstance(row, list) and len(row) == first_len for row in m):
        raise ValueError(first_len == 0 and 'ragged' or 'bad matrix')
    return [[row[c] for row in m] for c in range(first_len)]
