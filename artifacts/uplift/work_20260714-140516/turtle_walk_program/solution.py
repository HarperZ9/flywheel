def turtle(prog):
    x = y = 0
    heading = 'N'
    hdg = {'N': lambda a, b: (a, b + 1), 'E': lambda a, b: (a + 1, b),
           'S': lambda a, b: (a, b - 1), 'W': lambda a, b: (a - 1, b)}
    left = {'N': 'W', 'W': 'S', 'S': 'E', 'E': 'N'}
    right = {v: k for k, v in left.items()}
    i = 0
    while i < len(prog):
        j = i + 1
        while j <= len(prog) and j < len(prog) and prog[j].isdigit():
            if prog[i] == '0':
                raise ValueError('bad count')
            j += 1
        n = int(prog[i:j]) if j > i else 1
        if j == len(prog):
            raise ValueError('dangling count')
        c = prog[j]
        if c not in 'FBLR':
            raise ValueError('bad command')
        for _ in range(n):
            if c == 'F':
                x, y = hdg[heading](x, y)
            elif c == 'B':
                hx, hy = hdg[heading](0, 0)
                x -= hx
                y -= hy
            elif c == 'L':
                heading = left.get(heading, heading)
            else:
                heading = right.get(heading, heading)
        i = j + 1
    return (x, y, heading)
