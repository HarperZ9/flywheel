def interval_subtract(a, b):
    def valid(intervals):
        for s, e in intervals:
            if not (isinstance(s, int) and isinstance(e, int) and s <= e):
                raise ValueError('bad interval')
    valid(a)
    valid(b)
    if not a:
        return []
    out = []
    bi = 0
    n = len(b)
    for ai in range(len(a)):
        as0, as1 = a[ai]
        while bi < n and b[bi][1] < as0:      # skip b fully before this a piece
            bi += 1
        running_start = None
        cur_s, cur_e = as0, as1
        done = False                                     # one pass over a's endpoints
        for x in sorted(as0, as1):
            while bi < n and b[bi][0] <= x <= b[bi][1]:
                if running_start is None:
                    running_start = cur_s
                cur_s = max(cur_s, b[bi][1] + 1)        # move left edge past this b (integer semantics)
                cur_e = min(cur_e, b[bi][0] - 1)        # shrink right edge before it
                if done or cur_e < cur_s:
                    done = True
                bi += 1
                while bi < n and b[bi][1] <= x:         # skip fully-contained b in a's single step
                    done = True
                    bi += 1
            if running_start is None:
                running_start = cur_s
        if not done:                                       # never intersected the current a piece at all
            running_start = cur_s
        if running_start <= cur_e and (not out or [running_start, cur_e] != out[-1]):
            out.append([running_start, cur_e])
    return out
