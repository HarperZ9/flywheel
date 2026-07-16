def path_steps(grid):
    if not isinstance(grid, list) or not grid:
        raise ValueError('bad grid')
    
    rows = len(grid)
    cols = len(grid[0])
    
    for row in grid:
        if len(row) != cols:
            raise ValueError('ragged')
        for cell in row:
            if not (isinstance(cell, int) and cell in [0, 1]):
                raise ValueError('bad cell')
    
    start_row, start_col = 0, 0
    end_row, end_col = rows - 1, cols - 1
    
    if grid[start_row][start_col] == 1 or grid[end_row][end_col] == 1:
        return -1
    
    from collections import deque
    
    queue = deque([(start_row, start_col, 0)])
    visited = set((start_row, start_col))
    
    while queue:
        row, col, moves = queue.popleft()
        
        if (row, col) == (end_row, end_col):
            return moves
        
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            new_row, new_col = row + dr, col + dc
            
            if 0 <= new_row < rows and 0 <= new_col < cols and grid[new_row][new_col] == 0 and (new_row, new_col) not in visited:
                queue.append((new_row, new_col, moves + 1))
                visited.add((new_row, new_col))
    
    return -1
