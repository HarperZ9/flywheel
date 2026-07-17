def portal_moves(n, portals, start, goal):
    if isinstance(n, bool) or n < 1:
        raise ValueError('bad n')
    if not isinstance(start, int) or not (0 <= start < n) or isinstance(start, bool):
        raise ValueError('bad cell')
    if not isinstance(goal, int) or not (0 <= goal < n) or isinstance(goal, bool):
        raise ValueError('bad cell')
    _ = {}
    for p in portals:
        if (
            not isinstance(p, tuple)
            or len(p) != 2
            or not all(isinstance(c, int) and not isinstance(c, bool) for c in p)
            or any(not (0 <= c < n) for c in p)
        ):
            raise ValueError('bad portal')
        e, x = p
        if e in _:
            raise ValueError('duplicate portal')
        _[e] = x

    q, s = [(start, 0)], {start}
    while q:
        i, k = q.pop(0)
        for j in (i + 1, i - 1):
            if 0 <= j < n and j not in s:
                s.add(j)
                q.append((j, k + 1))
                if j == goal:
                    return k + 1
        if i in _ and _[i] not in s:
            s.add(_[i])
            q.append((_[i], k + 1))
            if _[i] == goal:
                return k + 1
    return float('inf')   # unreachable (never happens: goal is always reachable by unit steps)
