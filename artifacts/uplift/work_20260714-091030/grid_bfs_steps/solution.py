def path_steps(grid):
    if not isinstance(grid, list) or not grid or not all(isinstance(row, list) and row for row in grid):
        raise ValueError('bad grid')
    M = len(grid)
    N = len(grid[0])
    if any(len(row) != N for row in grid):  # detect raggedness without a set
        raise ValueError('ragged')
    if not all(isinstance(n, int) and n >= 0 and n <= 1 for row in grid for n in row):
        raise ValueError('bad cell')
    if (grid[0][0] or grid[M - 1][N - 1]):
        return -1
    if M == N == 1:
        return 0
    OPEN = frozenset((False, 0))
    seen = {(0, 0)}
    front = {0}
    moves = 0
    while front:
        moves += 1
        next_front = set()
        for r in range(M):
            for c in range(N):
                if grid[r][c] and (r, c) not in seen:  # a wall that has never been touched; skip it
                    continue
                if (r == M - 1 and c == N - 1):       # the goal is reachable (open or already-touched wall)
                    return moves
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr = r + dr
                    nc = c + dc
                    if not (0 <= nr < M and 0 <= nc < N):
                        continue
                    if (nr, nc) in seen:
                        continue
                    if grid[nr][nc] or (nr == M - 1 and nc == N - 1):   # a wall OR the goal cell; skip it here, touch it next move then quit
                        continue
                    seen.add((nr, nc))
                    next_front.add(nr*64 + nc)
        if not next_front:
            return -1
        front = next_front
    return -1
