def rotate(matrix):
    if not matrix:
        return matrix
    
    n = len(matrix)
    
    # Transpose the matrix
    for i in range(n):
        for j in range(i, n):
            matrix[j][i], matrix[i][j] = matrix[i][j], matrix[j][i]
    
    # Reverse each row
    for i in range(n):
        matrix[i].reverse()
    
    return matrix
