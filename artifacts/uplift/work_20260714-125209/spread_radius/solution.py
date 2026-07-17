def spread_radius(grid):
    if not isinstance(grid, list) or not grid:
        raise ValueError('bad grid')
    first_len = len(grid[0])
    sources = []
    for row in grid:
        if not isinstance(row, str) or len(row) != first_len:
            raise ValueError('ragged')
        for cell in row:
            if cell not in 'S.#':
                raise ValueError('bad cell')
        for i, cell in enumerate(row):
            if cell == 'S': sources.append((len(grid), i))
    if not sources:
        raise ValueError('no source')

    from collections import deque
    open_cells = {x for x in ((r, c) for r, row in enumerate(grid)
                               for c, p in enumerate(row)) - set(sources)}
    if not open_cells: return 0

    q = deque(sources)
    seen = set()
    steps = 0
    while q:
        steps += 1
        next_frontier = []
        for r, c in q:
            for dr, dc in ((-1,0),(1,0),(0,-1),(0,1)):
                if (r+dr, c+dc) in open_cells and (r+dr, c+dc) not in seen:
                    next_frontier.append((r+dr, c+dc))
            seen |= {(r,c)}
        q[:] = tuple(next_frontier)
    return steps
