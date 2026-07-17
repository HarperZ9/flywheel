def rotate(matrix):
    n = len(matrix)
    for layer in range(n // 2):
        first, last = layer, n - 1 - layer
        for i in range(first, last):
            offset = i - first
            # Save top element
            top = matrix[first][i]
            
            # Move left element to top
            matrix[first][i] = matrix[last - offset][first]
            
            # Move bottom element to left
            matrix[last - offset][first] = matrix[last][last - offset]
            
            # Move right element to bottom
            matrix[last][last - offset] = matrix[i][last]
            
            # Assign saved top element to right
            matrix[i][last] = top
    
    return matrix
