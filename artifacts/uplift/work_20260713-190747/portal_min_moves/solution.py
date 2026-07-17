def portal_moves(n, portals, start, goal):
    if not isinstance(n, int) or n < 1:
        raise ValueError('bad n')
    if not (0 <= start <= n - 1) or not (0 <= goal <= n - 1):
        raise ValueError('bad cell')
    if start > goal:
        raise ValueError('start must be before goal')

    # Validate portals
    portal_set = set()
    for entry, exit_ in portals:
        if not isinstance(entry, int) or not isinstance(exit_, int) or entry < 0 or exit_ < 0 or entry >= n or exit_ >= n:
            raise ValueError('bad portal')
        if (entry, exit_) in portal_set or (exit_, entry) in portal_set:
            raise ValueError('duplicate portal')
        portal_set.add((entry, exit_))

    visited = set()
    queue = [(start, 0)]
    
    while queue:
        current, moves = queue.pop(0)
        if current == goal:
            return moves
        visited.add(current)

        for entry, exit_ in portals:
            if current == entry:
                if exit_ not in visited:
                    queue.append((exit_, moves + 1))
                continue

            # Move to the adjacent cell (left or right)
            next_cell = current - 1 if current > 0 else None
            prev_cell = current + 1 if current < n - 1 else None
            if next_cell is not None and next_cell not in visited:
                queue.append((next_cell, moves + 1))
            if prev_cell is not None and prev_cell not in visited:
                queue.append((prev_cell, moves + 1))

    return -1  # Unreachable goal (shouldn't happen given problem constraints)
