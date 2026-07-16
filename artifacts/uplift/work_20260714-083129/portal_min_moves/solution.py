def portal_moves(n, portals, start, goal):
    if not isinstance(n, int) or n < 1:
        raise ValueError('bad n')
    
    if not (0 <= start < n and 0 <= goal < n):
        raise ValueError('bad cell')

    unique_portals = set()
    for entry, exit in portals:
        if not (isinstance(entry, int) and isinstance(exit, int)):
            raise ValueError('bad portal')
        if entry == exit or (entry, exit) in unique_portals:
            raise ValueError('duplicate portal')
        unique_portals.add((entry, exit))
    
    # Validate start and goal positions
    if not (0 <= start < n):
        raise ValueError('bad cell')

    if goal == start:
        return 0

    moves = [start]

    while start != goal:
        next_positions = set()
        for position in moves:
            if position > -1 and position < n:  # Moving to the left
                next_positions.add(position - 1)
            if position + 1 > -1 and position + 1 < n:  # Moving to the right
                next_positions.add(position + 1)

        for position in next_positions:
            for entry, exit in portals:
                if entry == position:
                    next_positions.add(exit)
        
        moves = list(next_positions)
        moves.sort()

    return len(moves)
