def matrix_shape(m):
    if not isinstance(m, list):
        raise ValueError("not a list")
    
    if not m:
        raise ValueError("empty")

    num_rows = len(m)
    first_row_length = len(m[0])
    
    for i in range(num_rows):
        if not isinstance(m[i], list):
            raise ValueError(f"row {i} not list")
        
        row_length = len(m[i])
        
        if row_length != first_row_length:
            raise ValueError("ragged")

        for j, cell in enumerate(m[i]):
            if not (isinstance(cell, int) or isinstance(cell, float)):
                raise ValueError(f"bad cell {j} of row {i}")

    return num_rows, first_row_length
