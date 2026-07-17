def transpose(m):
    if not isinstance(m, list):
        raise ValueError('bad matrix')
    
    for row in m:
        if not isinstance(row, list):
            raise ValueError('bad matrix')
    
    first_row_length = len(next(iter(m)))
    if any(len(row) != first_row_length for row in m):
        raise ValueError('ragged')

    transposed_matrix = [[None for _ in range(len(m))] for _ in range(len(m[0]))]
    
    for i, row in enumerate(m):
        for j, val in enumerate(row):
            transposed_matrix[j][i] = val

    return transposed_matrix
