from __future__ import annotations


def path_steps(grid: list[list[int]]) -> int:
    if not isinstance(grid, list) or len(grid) == 0:
        raise ValueError("bad grid")
    first = grid[0]
    if not isinstance(first, list) or len(first) == 0:
        raise ValueError("bad grid")

    height, width = len(grid), len(first)
    for r, row in enumerate(grid):
        if not isinstance(row, list) or len(row) != width:
            raise ValueError("ragged")
        for c, cell in enumerate(row):
            if (
                not isinstance(cell, int)
                or cell < 0
                or (cell not in (0, 1))
                or isinstance(cell, bool)
            ):
                raise ValueError(f"bad cell at ({r},{c}): {repr(cell)}")

    if grid[0][0] != 0 or grid[-1][-1] != 0:
        return -1

    # BFS: queue of (row, col, moves_so_far). Moves are half the path length.
    seen = {(0, 0)}
    q = [(0, 0, 0)]
    while q:
        r, c, moves = q.pop(0)
        for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if (
                0 <= nr < height
                and 0 <= nc < width
                and grid[nr][nc] == 0
                and (nr, nc) not in seen
            ):
                seen.add((nr, nc))
                if (nr, nc) == (height - 1, width - 1):
                    return moves + 1
                q.append((nr, nc, moves + 1))
    return -1
