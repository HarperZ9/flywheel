def matrix_shape(m):
    if not isinstance(m, list):
        raise ValueError('not a list')
    if not m:
        raise ValueError('empty')
    
    row_length = None
    for i, row in enumerate(m):
        if not isinstance(row, list):
            raise ValueError('row not list')
        if not row:
            raise ValueError('empty row')
        if row_length is None:
            row_length = len(row)
        elif len(row) != row_length:
            raise ValueError('ragged')
        
        for j, cell in enumerate(row):
            if not (isinstance(cell, int) or isinstance(cell, float)):
                raise ValueError(f'bad cell at ({i}, {j})')
    
    return (len(m), row_length)
