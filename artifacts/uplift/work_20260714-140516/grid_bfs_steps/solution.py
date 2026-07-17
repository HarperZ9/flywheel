def path_steps(grid):
    if not isinstance(grid, list) or not grid or not all(isinstance(row, list) and row for row in grid):
        raise ValueError('bad grid')
    n = len(grid)
    m = len(grid[0])
    for i, row in enumerate(grid):
        if len(row) != m:
            raise ValueError('ragged')
        for cell in row:
            if not isinstance(cell, int) or cell not in {0, 1}:
                raise ValueError('bad cell')
    if grid[0][0] == 1 or grid[-1][-1] == 1:
        return -1
    moves = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    queue = [(0, 0, 0)]
    seen = {(0, 0)}
    while queue:
        i, j, c = queue.pop(0)
        if i == n - 1 and j == m - 1:
            return c
        for di, dj in moves:
            x, y = i + di, j + dj
            if 0 <= x < n and 0 <= y < m and grid[x][y] == 0 and (x, y) not in seen:
                seen.add((x, y))
                queue.append((x, y, c + 1))
    return -1
