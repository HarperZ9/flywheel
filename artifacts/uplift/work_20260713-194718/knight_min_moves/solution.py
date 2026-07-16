def knight_moves(n: int, start: tuple[int, int], goal: tuple[int, int]) -> int:
    if not isinstance(n, int) or not (isinstance(start, tuple) and len(start) == 2 and 
                                        all(isinstance(i, int) and 0 <= i < n for i in start + goal)):
        raise ValueError('bad board')
    
    row_diffs = [2, 1], [-1, -2], [1, -2], [2, -1], [2, 1], [1, 2], [-1, 2], [-2, 1]
    
    def is_valid_move(row: int, col: int) -> bool:
        return 0 <= row < n and 0 <= col < n

    queue = [(start[0], start[1])]
    visited = {tuple(start)}
    steps = 0
    
    while queue:
        new_queue = []
        
        for r, c in queue:
            if (r, c) == goal:
                return steps
            for dr, dc in row_diffs:
                nr, nc = r + dr, c + dc
                if is_valid_move(nr, nc) and tuple((nr, nc)) not in visited:
                    visited.add(tuple((nr, nc)))
                    new_queue.append((nr, nc))
        
        queue = new_queue
        steps += 1
    
    return -1
