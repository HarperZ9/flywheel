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

    distance = {}
    q = list(sources)
    while q:
        r0, c0 = q.pop(0)
        for r1, c1 in ((r0 - 1, c0), (r0 + 1, c0), (r0, c0 - 1), (r0, c0 + 1)):
            if not (0 <= r1 < len(grid) and 0 <= c1 < first_len):
                continue
            if grid[r1][c1] == '#':
                continue
            key = f'{r1},{c1}'
            if key in distance:
                continue
            distance[key] = distance.get(f'{r0},{c0}', 0) + 1
            q.append((r1, c1))

    out = []
    for r in range(len(grid)):
        for c in range(first_len):
            if grid[r][c] == '.':
                out.append(distance.get(f'{r},{c}') or float('inf'))
    return max(out) if out and min(out) < float('inf') else (0 if out else -1)
