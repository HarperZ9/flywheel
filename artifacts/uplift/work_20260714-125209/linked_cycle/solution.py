def has_cycle(nxt):
    if not isinstance(nxt, list): raise ValueError('bad link')
    if len(nxt) == 0: return False
    for i in range(len(nxt)):
        x = nxt[i]
        if not isinstance(x, int): raise ValueError('bad link')
        if x != -1 and not (0 <= x < len(nxt)): raise ValueError('bad link')
    seen = set()
    u = 0
    while u != -1:
        if u in seen: return True
        next_u = nxt[u]
        seen.add(u)
        u = next_u # (next_u was already checked; loop never visits a bad-link node)
    return False
