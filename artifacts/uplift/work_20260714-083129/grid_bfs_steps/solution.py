def path_steps(grid):
    if not all(len(row) == len(grid[0]) for row in grid):
        raise ValueError('ragged')
    
    for row in grid:
        if any(not isinstance(cell, int) or cell not in (0, 1) for cell in row):
            raise ValueError('bad cell')

    def is_open(r, c):
        return r >= 0 and r < len(grid) and c >= 0 and c < len(grid[0]) and grid[r][c] == 0

    @cache
    def dp(r, c):
        if not is_open(r, c): 
            return float('inf')
        if r == len(grid) - 1 and c == len(grid[0]) - 1:
            return 1
        moves = min(dp(r + dr, c + dc) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))) + 1
        return moves

    result = dp(0, 0)
    return min(result, float('inf')) if result < float('inf') else -1
