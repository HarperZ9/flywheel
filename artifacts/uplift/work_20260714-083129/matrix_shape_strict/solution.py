def matrix_shape(m):
    if not isinstance(m, list):
        raise ValueError('not a list')
    
    if not m:
        raise ValueError('empty')

    num_rows = len(m)
    first_row_length = len(m[0])
    
    for row in m:
        if not isinstance(row, list):
            raise ValueError('row not list')
        
        if not row:
            raise ValueError('empty row')
            
        if len(row) != first_row_length:
            raise ValueError('ragged')
        
        for cell in row:
            if isinstance(cell, bool):
                raise ValueError('bad cell')

    return num_rows, first_row_length
