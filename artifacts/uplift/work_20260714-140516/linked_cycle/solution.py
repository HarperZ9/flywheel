def has_cycle(nxt):
    if not isinstance(nxt, list):
        raise ValueError('nxt must be a list')
    n = len(nxt)
    for i in range(n):
        v = nxt[i]
        if not isinstance(v, int):
            raise ValueError('bad link')
        if v != -1 and (v < 0 or v >= n):
            raise ValueError('bad link')
    s = set()
    at = 0
    while True:
        if at == -1:
            return False
        if at in s:
            return True
        s.add(at)
        at = nxt[at]
