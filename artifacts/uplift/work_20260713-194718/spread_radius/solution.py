def spread_radius(grid):
    if not isinstance(grid, list) or len(grid) == 0:
        raise ValueError('bad grid')
    
    # Check if rows are of varying lengths
    row_lengths = set(len(row) for row in grid)
    if len(row_lengths) > 1:
        raise ValueError('ragged')

    # Function to check the validity of each cell
    def is_valid_cell(cell):
        return cell == 'S' or cell.isspace() or cell == '#'
    
    # Check each character in the grid for valid values
    for row_idx, row in enumerate(grid):
        for col_idx, cell in enumerate(row):
            if not is_valid_cell(cell):
                raise ValueError('bad cell')

    # Find all sources (S)
    sources = []
    for i, row in enumerate(grid):
        for j, cell in enumerate(row):
            if cell == 'S':
                sources.append((i, j))
    
    # If no source found
    if not sources:
        return 0

    def bfs(start):
        queue = [(start, 0)]
        visited = set([start])
        while queue:
            (x, y), time = queue.pop(0)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < len(grid) and 0 <= ny < len(grid[0]) and grid[nx][ny] != '#' and (nx, ny) not in visited:
                    if grid[nx][ny] == ' ':
                        return time + 1
                    visited.add((nx, ny))
                    queue.append(((nx, ny), time + 1))
        return float('inf')

    # Calculate the spread radius
    max_radius = -1
    for source in sources:
        radius = max(bfs(source) if bfs(source) != float('inf') else -1, max_radius)
        if radius == -1: 
            break
        max_radius = radius

    return max_radius
