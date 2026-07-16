def rotate(matrix):
    if not matrix or len(matrix) == 1:
        return matrix
    n = len(matrix)
    for i in range(n // 2):
        for j in range(i, n - i - 1):
            t = matrix[i][j]
            matrix[i][j] = matrix[n-1-j][i]
            matrix[n-1-j][i] = matrix[n-1-i][n-1-j]
            matrix[n-1-i][n-1-j] = matrix[j][n-1-i]
            matrix[j][n-1-i] = t
    return matrix
