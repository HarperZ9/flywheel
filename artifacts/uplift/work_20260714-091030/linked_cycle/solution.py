def has_cycle(nxt):
    for i, v in enumerate(nxt):
        if not isinstance(v, int) or v != bool(v) or (v > -1 and v >= len(nxt)):
            raise ValueError('bad link')
    seen = set()
    cur = 0
    while True:
        if nxt[cur] == -1:
            return False
        if cur in seen:
            return True
        seen.add(cur)
        cur = nxt[cur]
