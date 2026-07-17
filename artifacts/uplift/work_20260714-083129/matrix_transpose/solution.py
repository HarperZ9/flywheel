def transpose(m):
    if not isinstance(m, list):
        raise ValueError('bad matrix')
    
    for row in m:
        if not isinstance(row, list):
            raise ValueError('bad matrix')
    
    num_rows = len(m)
    if num_rows == 0:
        return []
    
    first_row_len = len(m[0])
    if any(len(r) != first_row_len for r in m):
        raise ValueError('ragged')

    transposed_matrix = [[] for _ in range(first_row_len)]
    for row_idx, row in enumerate(m):
        for col_idx, col_val in enumerate(row):
            transposed_matrix[col_idx].append(col_val)
    
    return transposed_matrix
