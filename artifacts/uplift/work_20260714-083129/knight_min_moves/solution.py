def knight_moves(n, start, goal):
    if not isinstance(n, int) or n <= 0:
        raise ValueError('bad board')
    
    (sx, sy) = start
    (gx, gy) = goal
    
    if sx < 0 or sx >= n or sy < 0 or sy >= n or \
       gx < 0 or gx >= n or gy < 0 or gy >= n:
        raise ValueError('bad cell')
    
    # A knight can jump up to 3 squares in one direction
    def can_reach(x1, y1, x2, y2):
        return abs(x1 - x2) <= 2 and abs(y1 - y2) <= 2
    
    if start == goal:
        return 0
    
    visited = set()
    
    queue = [[start]]
    steps = 0
    
    while queue:
        path = queue.pop(0)
        
        node = path[-1]
        
        if node in visited:
            continue
        
        visited.add(node)
        
        for dx, dy in [(-2, -1), (-2, 1), (2, -1), (2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2)]:
            next_node = (node[0] + dx, node[1] + dy)
            
            if can_reach(node[0], node[1], next_node[0], next_node[1]):
                new_path = list(path)
                new_path.append(next_node)
                queue.append(new_path)
                
                if next_node == goal:
                    return steps + 1
                
        steps += 1
        
    return -1
