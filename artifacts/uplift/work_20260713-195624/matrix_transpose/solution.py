def transpose(m):
    """
    Transposes a given rectangular matrix (list). The input should be a list of lists,
    where each inner list represents a row in the matrix.
    
    Args:
        m: A 2D list, where each element is an inner list representing a row.

    Returns:
        A new 2D list that is the transpose of the input matrix. Note: The rows are
        swapped to get the correct column-wise structure from the original matrix.
    """
    # Check if all rows are not empty lists or if they have the same length
    if not m or (any(not isinstance(row, list) for row in m)):
        raise ValueError('bad matrix')
    
    n = len(m[0])  # Get the number of rows from the first row's index
    
    # Transpose the matrix by swapping elements
    return [row[:] for row in zip(*m)]
