def portal_moves(n, portals, start, goal):
    if not isinstance(n, int) or n < 1:
        raise ValueError('bad n')
    sn = {start}
    ok = set(range(n))
    for a in [start, goal]:
        if not (isinstance(a, int) and a >= 0 and a <= n - 1):
            raise ValueError('bad cell')
    pmap = {}
    seen = set()
    for pv in portals:
        if not isinstance(pv, tuple) or len(pv) != 2:
            raise ValueError('bad portal')
        e, x = pv
        if not (isinstance(e, int) and isinstance(x, int)):
            raise ValueError('bad portal')
        if e < 0 or e >= n or x < 0 or x >= n:
            raise ValueError('bad portal')
        if e in seen:
            raise ValueError('duplicate portal')
        pmap[e] = x
        seen.add(e)
    sn2 = set()
    moves = 0
    while True:
        moves += 1
        for i in sn:
            for a in [i - 1, i + 1]:
                if (a >= 0 and a <= n - 1) and a not in sn2:
                    sn2.add(a)
            if i in pmap and pmap[i] not in sn2:
                sn2.add(pmap[i])
        if goal in sn2:
            return moves
        sn, sn2 = sn2, set()
