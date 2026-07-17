def interval_subtract(a, b):
    def valid(iv):
        if iv and iv[0] > iv[1]:
            raise ValueError('bad interval')
        return iv

    a = [valid(x) for x in a]
    b = [valid(x) for x in b]
    if not a:
        return []
    out = []
    i, j = 0, 0
    lo, hi = None, None
    while i < len(a):
        ax, ay = a[i][0], a[i][1]
        while j < len(b) and b[j][1] < ax:
            j += 1
        if j == len(b):
            if lo is None:
                lo = ax
            hi = max(hi or (ax - 1), ay)
            i += 1
            continue
        bx, by = b[j][0], b[j][1]
        if ay < bx:
            if lo is None:
                lo = ax
            hi = max(hi or (ax - 1), ay)
            out.append([lo, hi])
            lo, hi = None, None
            i += 1
            continue
        jx = max(ax, bx)
        jy = min(ay, by)
        if lo is not None:
            out.append([lo, jx - 1])
        if ay == jy:   # a[i] consumed exactly; may consume b[j]
            i += 1
            if by == ay:
                j += 1
            continue
        if bx <= ax and by >= ay:
            raise ValueError('overlap')   # disjoint + sorted -> impossible here
        if jx > lo:                 # some of the already-pinned a[i] remains
            out.append([lo, jx - 1])
        lo = max(lo or jy + 1, jy + 1)
        ax = max(ax, by + 1)        # how much of a[i] is unsatisfied; back to i
        if ax <= ay:
            continue
        raise ValueError('overlap')   # disjoint + sorted -> impossible here
    return out
