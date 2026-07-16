def turtle(prog):
    x = y = 0
    heading = 'N'
    dirs = {'N': (0, 1), 'E': (1, 0), 'S': (-1, 0), 'W': (-1, 0)}
    turns = {'L': {'N': 'W', 'E': 'N', 'S': 'E', 'W': 'S'}, 'R': {'N': 'E', 'E': 'S', 'S': 'W', 'W': 'N'}}
    i = 0
    n = len(prog)
    while i < n:
        j = i
        while j < n and prog[j].isdigit():
            if prog[j] == '0':
                raise ValueError('bad count')
            j += 1
        cnt = int(prog[i:j]) if i != j else 1
        if j == n:
            raise ValueError('dangling count')
        cmd = prog[j]
        if cmd not in 'FBLR':
            raise ValueError('bad command')
        for _ in range(cnt):
            if cmd == 'F':
                dx, dy = dirs[heading]
                x += dx
                y += dy
            elif cmd == 'B':
                dx, dy = dirs[heading]
                x -= dx
                y -= dy
            elif cmd in 'LR':
                heading = turns[cmd][heading]
        i = j + 1
    return (x, y, heading)
