def count_islands(grid):
    def is_valid(x, y):
        return 0 <= x < len(grid) and 0 <= y < len(grid[0]) and grid[x][y] == 1
    
    def dfs(x, y):
        if not is_valid(x, y):
            return 
        grid[x][y] = 0  # Mark as visited
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        for dx, dy in directions:
            dfs(x + dx, y + dy)
    
    if not grid or not grid[0]:
        return 0
    
    count = 0
    for i in range(len(grid)):
        for j in range(len(grid[0])):
            if is_valid(i, j):
                dfs(i, j)
                count += 1
                
    return count
