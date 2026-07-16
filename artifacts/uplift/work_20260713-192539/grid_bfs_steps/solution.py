def path_steps(grid):
    if not all(len(row) == len(grid[0]) for row in grid):
        raise ValueError('ragged')
    
    def value_error(cell):
        if not isinstance(cell, int) or (cell != 0 and cell != 1):
            raise ValueError('bad cell')
        return cell
    
    def check_errors(grid):
        for row_index, row in enumerate(grid):
            for col_index, cell in enumerate(row):
                try:
                    value_error(grid[row_index][col_index])
                except Exception as e:
                    print(f"Error at {row_index}, {col_index}: {e}")
                    return -1
        return grid
    
    if not all(isinstance(row, list) and len(row) == len(grid[0]) for row in check_errors(grid)):
        raise ValueError('bad grid')
    
    def dfs(x, y, path_len):
        if x < 0 or x >= len(grid) or y < 0 or y >= len(grid[0]):
            return float('inf')  # Out of bounds
        if grid[x][y] == 1:
            return float('inf')  # Wall
        if (x, y) in visited:
            return float('inf')  # Already visited this cell
        visited.add((x, y))
        
        current_path_len = path_len + 1
        
        next_moves = [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]
        for next_x, next_y in next_moves:
            if grid[next_x][next_y] == 0:
                current_path_len = dfs(next_x, next_y, current_path_len)
        
        visited.remove((x, y))
        
        return min(current_path_len, float('inf'))
    
    # Initialize the starting point
    x, y = (0, 0)
    grid[x][y] = -2  # No need to check this cell as it's already part of visited
    
    try:
        shortest_moves = dfs(*tuple(x for row in grid[:x+1] for x in range(len(row))), 0)
    except Exception as e:
        return -1  # If any error occurs, no path is possible
    if shortest_moves == float('inf'):
        return -1  # No valid route found
    
    return shortest_moves - 2  # Subtract the initial two visits to the start and end points
