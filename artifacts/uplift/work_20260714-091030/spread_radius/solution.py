def spread_radius(grid):
    if not isinstance(grid, list) or not grid:
        raise ValueError('bad grid')
    n = len(grid)
    m = 0 if n == 1 else len(grid[0])
    if not isinstance(m, int) or m < 1:
        raise ValueError('ragged')
    for r in grid:
        if not isinstance(r, str):
            raise ValueError('bad grid')
        if len(r) != m:
            raise ValueError('ragged')
        for c in r:
            if c not in 'S.#':
                raise ValueError('bad cell')
    sources = [(i, j)
               for i, row in enumerate(grid)
               for j, v in enumerate(row) if v == 'S']
    if not sources:
        raise ValueError('no source')
    open_cells = {(i, j)
                  for i, row in enumerate(grid)
                  for j, v in enumerate(row) if v == '.'}
    if not open_cells:
        return 0
    d = [[None] * m for _ in range(n)]
    at = sources
    steps = 0
    done = False
    while not done and at:
        next_at = set()
        done = True
        for i, j in sorted(at):
            for x, y in (i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1):
                if not(0 <= x < n and 0 <= y < m) or grid[x][y] == '#':
                    continue
                if d[x][y] is None:
                    done = False
                    d[x][y] = steps + 1
                    next_at.add((x, y))
        at = next_at
        steps += 1
    return max(d[i][j] for i, j in open_cells) if done else -1
