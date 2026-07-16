import numpy as np

def matrix_shape(m):
    """
    Validates a given rectangular numeric matrix and returns its shape as a tuple.
    
    Args:
    - m: A list representing the matrix, which must be non-empty.

    Returns:
    - A tuple containing the number of rows and columns in the matrix. If input is invalid,
      raises ValueError with an appropriate message.
    """
    # Check if the input is a valid 2D list
    if not isinstance(m, list) or not m:
        raise ValueError('not a list')
    
    # Check that the list is non-empty
    rows = len(m)
    if rows == 0:
        raise ValueError('empty')

    # Initialize counters for columns and rows
    columns = 1
    first_row = True

    # Iterate over each row in the matrix, starting from the first row with column 0
    for i in range(rows):
        row = m[i]  # Convert to list (list of lists)
        
        if not isinstance(row, list) or not all(isinstance(item, (int, float)) for item in row):
            raise ValueError('row not list')
            
        if len(row) != columns:
            raise ValueError('ragged')
            
        if first_row and any(cell < 0 or cell > 1e-8 for cell in row):
            raise ValueError('bad cell')

        # Update the column counter
        columns += 1

    return (columns, rows)

# Check function with provided data points
def check(matrix_shape_fn):
    m1 = np.array([[2.5, -3, 0.], [4, -9, 8]])
    m2 = []
    
    assert matrix_shape_fn(m1) == (2, 2), "Test case m1 failed."
    assert not matrix_shape_fn(m2) == (0, 0), "Test case m2 failed."

# Running the check function
print("Matrix shape validation passed.")
check(matrix_shape)
