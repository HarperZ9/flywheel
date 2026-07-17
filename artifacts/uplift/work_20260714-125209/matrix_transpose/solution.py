def transpose(m):
    if not isinstance(m, list):
        raise ValueError('bad matrix')
    if len(m) == 0:
        return []
    if any(not isinstance(row, list) for row in m):
        raise ValueError('bad matrix')
    first_len = len(m[0])
    if any(len(row) != first_len for row in m):
        raise ValueError('ragged')
    result = [[m[r][c] for r in range(len(m))] for c in range(first_len)]
    return result
