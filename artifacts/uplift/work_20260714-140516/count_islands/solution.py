def count_islands(grid):
    def dfs(r, c):
        if r < 0 or r >= len(grid) or c < 0 or c >= len(grid[0]) or seen[r][c] or grid[r][c] == 0:
            return
        seen[r][c] = True
        for nr, nc in ((r-1,c), (r+1,c), (r,c-1), (r,c+1)):
            dfs(nr, nc)
    if not grid or not grid[0]:
        return 0
    seen = [[False]*len(grid[0]) for _ in range(len(grid))]
    count = 0
    for r in range(len(grid)):
        for c in range(len(grid[0])):
            if not seen[r][c] and grid[r][c] == 1:
                dfs(r, c)
                count += 1
    return count
