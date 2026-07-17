def spread_radius(grid):
    if not isinstance(grid, list) or len(grid) == 0:
        raise ValueError('bad grid')

    for row in grid:
        if not isinstance(row, str) or len(row) != len(grid[0]):
            raise ValueError('ragged')

    def is_valid_cell(cell):
        return cell in ['.', 'S']
    
    sources = []
    for i, row in enumerate(grid):
        for j, cell in enumerate(row):
            if grid[i][j] == 'S':
                sources.append((i, j))
            elif not is_valid_cell(cell):
                raise ValueError('bad cell')

    if len(sources) == 0:
        raise ValueError('no source')
    
    def get_neighbors(x, y):
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < len(grid) and 0 <= ny < len(grid[0]) and grid[nx][ny] != '#':
                yield nx, ny

    max_dist = 0
    visited = set()
    
    for source in sources:
        queue = [(source, 0)]
        while queue:
            current, dist = queue.pop(0)
            if is_valid_cell(grid[current[0]][current[1]]) and (current not in visited):
                visited.add(current)
                max_dist = max(max_dist, dist)
                for neighbor in get_neighbors(*current):
                    queue.append((neighbor, dist + 1))
    
    return max_dist if grid[visited.pop()][visited.pop()] == '.' else -1
