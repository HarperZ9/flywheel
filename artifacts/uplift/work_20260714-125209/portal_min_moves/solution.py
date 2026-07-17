def portal_moves(n, portals, start, goal):
    # Validate n first: must be an int >= 1, not a bool.
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError('bad n')
    if not isinstance(start, int) or isinstance(start, bool) \
            or start < 0 or start >= n:
        raise ValueError('bad cell')
    if not isinstance(goal, int) or isinstance(goal, bool) \
            or goal < 0 or goal >= n:  # check goal AFTER start
        raise ValueError('bad cell')
    exts = {}
    for p in portals:
        if not isinstance(p, tuple) or len(p) != 2:
            raise ValueError('bad portal')
        i, o = p
        if (not isinstance(i, int) or isinstance(i, bool)
                or not isinstance(o, int) or isinstance(o, bool)):
            raise ValueError('bad portal')
        if i < 0 or i >= n or o < 0 or o >= n:
            raise ValueError('bad portal')
        if i in exts:              # duplicate entry -> error
            raise ValueError('duplicate portal')
        exts[i] = o                # remember exit for that entry
    if start == goal:
        return 0
    here, m, seen = [start], 1, {start}
    while here:
        nxt = []
        for i in here:             # from each cell reachable this round..
            if exts.get(i) is not None and exts[i] not in seen:
                if exts[i] == goal:
                    return m
                seen.add(exts[i])
                nxt.append(exts[i])  # ..jump portal exit (if unseen)
            for j in i - 1, i + 1:  # ..move one cell left/right
                if 0 <= j < n and j not in seen:
                    if j == goal:
                        return m
                    seen.add(j)
                    nxt.append(j)
        here = nxt                 # round done; extend from all new cells
        m += 1
