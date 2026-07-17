def spread_radius(grid):
    def calculate_distance(source, target):
        # The Manhattan distance between two points is the sum of the absolute differences of their coordinates.
        x1, y1 = source
        x2, y2 = target
        return abs(x2 - x1) + abs(y2 - y1)
    
    if not grid:
        raise ValueError("bad grid")
    
    rows = len(grid)
    if rows == 0 or all(c == 'S' for c in row for row in grid):
        raise ValueError('no source')
    
    total_steps = 0
    max_distance = -1
    
    for i, row in enumerate(grid):
        # Check the first cell of each row.
        if row[0] == 'S':
            source = (i, 0)
            target = (i, len(row) - 1)
            
            while source != target:
                total_steps += 1
                min_distance = calculate_distance(source, target)
                
                # If the current step covers a wall or out of bounds, adjust boundaries.
                if ((source[0] == 0 and row[source[1]] == 'S') or (target[0] == len(grid) - 1 and row[target[1]] == 'S')):
                    source = (i, target[0])
                    target = (i, len(row) - 1)
                else:
                    # The current step covers a wall.
                    if (source[1] != target[1]) or abs(source[0] - target[0]) > 1:
                        max_distance = min(max_distance, calculate_distance(source, target))
                        
                source = (i, row.index('S') + 1)
                
            # Record the last step.
            if source == target:
                total_steps += 1
            else:
                max_distance = -1
    
    return max_distance
