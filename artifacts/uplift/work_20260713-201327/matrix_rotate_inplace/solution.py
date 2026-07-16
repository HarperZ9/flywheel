def rotate(matrix):
    """
    Rotate a given 2D list (matrix) 90 degrees clockwise in place.

    Args:
        matrix: A 2D list of integers representing a square matrix.
    
    Returns:
        rotated_matrix: The same 2D list object after rotating, but not in place.
    """

    n = len(matrix)
    for i in range(n):
        for j in range(i + 1, n):
            matrix[i][j], matrix[j][i] = matrix[j][i], matrix[i][j]

    # Reverse the direction of rotations
    for i in range(n // 2):
        for j in range(n - 1):
            temp = matrix[i][j]
            matrix[i][j] = matrix[n - (i + n // 2)][n - 1 - j]
            matrix[n - (i + n // 2)][n - 1 - j] = temp
