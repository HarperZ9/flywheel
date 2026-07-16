def transpose(m):
    if not isinstance(m, list):
        raise ValueError('bad matrix')
    
    if len(m) == 0:
        return []
    
    for row in m:
        if not isinstance(row, list):
            raise ValueError('bad matrix')
        if len(row) != len(m[0]):
            raise ValueError('ragged')
    
    return [list(row) for row in zip(*m)]
