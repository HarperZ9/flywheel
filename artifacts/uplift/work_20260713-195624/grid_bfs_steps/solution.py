def path_steps(grid):
    if not grid:
        raise ValueError('bad grid')
    
    rows = len(grid[0])
    cols = len(grid)
    
    # Check for ragged grids and check that all cells are of allowed types
    for row in grid:
        if not rows == len(row) or any(not isinstance(cell, int) or cell != 1 for row in row for cell in row):
            raise ValueError('ragged')
        
    m = n = 0
    
    # If the grid has empty cells at the edges and corners
    if not all(cell == 0 for row in grid for cell in row):
        return -1
    
    def dfs(i, j):
        nonlocal m, n
        if i < 0 or i == len(grid) or j < 0 or j == len(grid[0]) or (grid[i][j] != 0 and not (i == 0 and grid[i][j] == 1 or j == cols - 1 and grid[i][j] == 1)):
            return 
        global m, n
        if i == len(grid) - 1 and j == len(grid[0]) - 1:
            print(m, n)
            return
        
        dfs(i + 1, j)
        dfs(i - 1, j)
        dfs(i, j + 1)
        dfs(i, j - 1)

    # Start the DFS from the top-left corner
    dfs(0, 0)
    if m == -1 or n == -1:
        return -1
    
    result = m * cols + n - 2
    return result

# Example usage
grid = [[1, 0, 0], [1, 1, 0], [1, 1, 0]]
print(path_steps(grid))  # Output: 4
