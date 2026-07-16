def turtle(prog):
    state = [0, 0, 'N']  # Initial position and heading
    
    def parse_command(cmd):
        if cmd.isdigit():
            count = int(cmd)
            if cmd.startswith('0'):
                raise ValueError('bad count')
            if len(cmd) > len(prog) or prog[len(cmd)] not in 'FRBL':
                raise ValueError('dangling count' if len(cmd) == len(prog) else 'bad command')
            cmd = prog[len(cmd)]
            prog = prog[2:]  # Skip the number
        elif cmd not in 'FBRL':
            raise ValueError(f'bad command: {cmd}')
        
        return cmd, prog
    
    x, y, heading = state
    while prog:
        cmd, prog = parse_command(prog)
        if cmd == 'F':
            if heading == 'N': y += 1
            elif heading == 'S': y -= 1
            elif heading == 'E': x += 1
            elif heading == 'W': x -= 1
        elif cmd == 'B':
            if heading == 'N': y -= 1
            elif heading == 'S': y += 1
            elif heading == 'E': x -= 1
            elif heading == 'W': x += 1
        elif cmd == 'L':
            heading = {'N': 'W', 'W': 'S', 'S': 'E', 'E': 'N'}[heading]
        elif cmd == 'R':
            heading = {'N': 'E', 'E': 'S', 'S': 'W', 'W': 'N'}[heading]
    
    return (x, y, heading)
