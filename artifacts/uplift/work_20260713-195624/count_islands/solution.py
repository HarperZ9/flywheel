def count_islands(grid):
    def dfs(i, j):
        if not 0 <= i < len(grid) or not 0 <= j < len(grid[0]) or grid[i][j] == 0:
            return True

        grid[i][j] = 0

        # Check and visit the cell
        left, right, up, down = dfs(i - 1, j), dfs(i + 1, j), dfs(i, j - 1), dfs(i, j + 1)

        if left:
            return True
        if right:
            return True
        if up:
            return True
        if down:
            return True

        return False

    count = 0

    for i in range(len(grid)):
        for j in range(len(grid[0])):
            if grid[i][j] == 1 and dfs(i, j):
                count += 1

    return count
