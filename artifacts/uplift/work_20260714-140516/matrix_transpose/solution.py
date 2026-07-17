def transpose(m):
    if not isinstance(m, list):
        raise ValueError('bad matrix')
    if len(m) == 0:
        return []
    if not all(isinstance(row, list) for row in m):
        raise ValueError('bad matrix')
    first_len = len(m[0])
    if any(len(row) != first_len for row in m):
        raise ValueError('ragged')
    result = [[m[row][col] for row in range(len(m))] for col in range(first_len)]
    return result
