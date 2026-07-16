def knight_moves(n, start, goal):
    if not isinstance(n, int) or n < 1:
        raise ValueError('bad board')
    if not (isinstance(start, tuple) and len(start) == 2 and
            all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x < n for x in start)):
        raise ValueError('bad cell')
    if not (isinstance(goal, tuple) and len(goal) == 2 and
            all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x < n for x in goal)):
        raise ValueError('bad cell')
    
    if start == goal:
        return 0
    
    from collections import deque
    
    # Possible knight moves
    moves = [
        (2, 1), (2, -1), (-2, 1), (-2, -1),
        (1, 2), (1, -2), (-1, 2), (-1, -2)
    ]
    
    queue = deque([(start, 0)])
    visited = set([start])
    
    while queue:
        (row, col), steps = queue.popleft()
        if (row, col) == goal:
            return steps
        
        for move in moves:
            new_row, new_col = row + move[0], col + move[1]
            if 0 <= new_row < n and 0 <= new_col < n and (new_row, new_col) not in visited:
                visited.add((new_row, new_col))
                queue.append(((new_row, new_col), steps + 1))
    
    return -1
