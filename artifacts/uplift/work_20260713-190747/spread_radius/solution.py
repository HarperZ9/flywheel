def spread_radius(grid):
    if not isinstance(grid, list) or len(grid) == 0:
        raise ValueError('bad grid')
    
    rows = len(grid)
    cols = len(grid[0])
    
    for i in range(rows):
        if len(grid[i]) != cols:
            raise ValueError('ragged')
        for cell in grid[i]:
            if cell not in 'S.#.':
                raise ValueError('bad cell')
    
    sources = [(i, j) for i in range(rows) for j in range(cols) if grid[i][j] == 'S']
    if not sources:
        raise ValueError('no source')

    # Initialize the distance grid with infinity
    dist = [[float('inf')] * cols for _ in range(rows)]
    
    # Set the distance to 0 for all sources
    for src in sources:
        dist[src[0]][src[1]] = 0

    # Directions: right, down, left, up
    directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]

    # Perform BFS to find the minimum distance to any source for each cell
    queue = sources[:]
    visited = set(queue)
    
    while queue:
        new_queue = []
        for src in queue:
            for dir in directions:
                next_i, next_j = src[0] + dir[0], src[1] + dir[1]
                if 0 <= next_i < rows and 0 <= next_j < cols and grid[next_i][next_j] != '#' and (next_i, next_j) not in visited:
                    new_dist = dist[src[0]][src[1]] + 1
                    if new_dist < dist[next_i][next_j]:
                        dist[next_i][next_j] = new_dist
                        new_queue.append((next_i, next_j))
                        visited.add((next_i, next_j))
        queue = new_queue

    # Find the maximum distance to an open floor cell or return -1 if no open floor cells are reached
    max_distance = max([max(row) for row in dist])
    
    # Check if any open floor cell was reachable
    all_walls = all(cell == '#' for row in dist for cell in row)
    if all_walls:
        return 0
    
    return -1 if max_distance == float('inf') else max_distance
