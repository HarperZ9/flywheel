def portal_moves(n, portals, start, goal):
    if not isinstance(n, int) or n < 1:
        raise ValueError('bad n')
    
    if not (0 <= start < n and 0 <= goal < n):
        raise ValueError('bad cell')
    
    if start == goal:
        return 0

    # Check for invalid portals
    visited = [False] * n
    def has_duplicate_portals(portals, index=0):
        if index >= len(portals):
            return False
        
        entry, exit = portals[index]
        
        # Skip duplicates and already visited entries.
        if visited[entry]:
            return True
        elif visited[exit]:
            return True
        else:
            visited[entry] = True

        # Only check the valid portal that matches our current index.
        next_index = (index + 1) % len(portals)
        return has_duplicate_portals(portals, next_index)
    
    if has_duplicate_portals(portals):
        raise ValueError('duplicate portal')
    
    # Check all portals to find valid path
    for entry, exit in portals:
        visited[entry] = True
        
        if entry == start and (exit == goal or has_duplicate_portals([(exit, e) for e in range(n)], 0)):
            return 1
        elif entry != start and (visited[goal]):
            return 2

    # If the above failed, no valid path exists.
    raise ValueError('no path')
