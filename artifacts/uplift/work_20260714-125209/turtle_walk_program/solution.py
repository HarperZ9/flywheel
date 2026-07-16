def turtle(prog):
    x = y = 0
    heading = 'N'
    hdg = {'N': lambda a, b: (a, b + 1), 'E': lambda a, b: (a + 1, b),
           'S': lambda a, b: (a, b - 1), 'W': lambda a, b: (a - 1, b)}
    turn = {'N': {'L': 'W', 'R': 'E'}, 'E': {'L': 'N', 'R': 'S'},
            'S': {'L': 'E', 'R': 'W'}, 'W': {'L': 'S', 'R': 'N'}}
    i, n = 0, len(prog)
    while i < n:
        d_start = i
        while i < n and prog[i] in '0123456789':
            if prog[i] == '0':
                raise ValueError('bad count')
            i += 1
        cnt = int(prog[d_start:i]) if (i != d_start) else 1
        if i == n:
            raise ValueError('dangling count')
        c = prog[i]
        if c not in 'FBLR':
            raise ValueError('bad command')
        for _ in range(cnt):
            if c in 'LR':
                heading = turn[heading][c]
            elif c == 'F':
                x, y = hdg[heading](x, y)
            else:
                opp = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}[heading]
                x, y = hdg[opp](x, y)
        i += 1
    return (x, y, heading)
