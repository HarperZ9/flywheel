def knight_moves(n, start, goal):
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError('bad board')
    def bad(cell, what):
        return (not isinstance(cell, tuple)
                or len(cell) != 2
                or any(not isinstance(c, int) or isinstance(c, bool) for c in cell)
                or not (0 <= cell[0] < n and 0 <= cell[1] < n))
    if bad(start, 'start'):
        raise ValueError('bad cell')
    if bad(goal, 'goal'):
        raise ValueError('bad cell')
    if start == goal:
        return 0
    moves = ((2, 1), (1, 2), (-1, 2), (-2, 1), (-2, -1), (-1, -2), (1, -2), (2, -1))
    seen = {start}
    q = [(start, 0)]
    while q:
        cell, d = q.pop(0)
        for dx, dy in moves:
            next_ = (cell[0] + dx, cell[1] + dy)
            if next_ == goal:
                return d + 1
            if bad(next_, 'next'):
                continue
            if next_ not in seen:
                seen.add(next_)
                q.append((next_, d + 1))
    return -1
