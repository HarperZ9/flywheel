def count_islands(grid):
    """
    Given a 2D list of 0/1 integers, return the number of islands of 1s connected 4-directionally.
    An empty grid returns 0. The input grid must NOT be modified.

    :param grid: List[List[int]]
    :return: int
    """
    if not grid or not grid[0]:
        return 0

    rows, cols = len(grid), len(grid[0])
    visited = set()

    def dfs(r, c):
        if (r, c) in visited:
            return
        visited.add((r, c))
        for dr, dc in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == 1:
                dfs(nr, nc)

    island_count = 0
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == 1 and (r, c) not in visited:
                dfs(r, c)
                island_count += 1

    return island_count
