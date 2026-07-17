def wrap_text(s, width):
    if not isinstance(width, int) or width <= 0:
        raise ValueError('bad width')
    out = []
    if not s.strip():
        return out
    words = [w for part in s.splitlines() for w in ''.join(part).split()]
    curr = []
    curr_len = 0
    def flush(): nonlocal curr; out.append(' '.join(curr)); del curr[:]; nonlocal curr_len; curr_len = 0
    while words:
        wd = len(words[0])
        if wd > width:
            if curr: flush()
            for i in range(0, wd, width):
                out.append(words[0][i:i+width])
            del words[0]
            continue
        if curr_len + (1 if curr else 0) + wd > width:
            flush()
        if curr: curr.append(' ')
        curr.append(words[0]); curr_len += len(words[0]) + (1 if curr and len(curr) > 1 else 0); del words[0]
    return out
