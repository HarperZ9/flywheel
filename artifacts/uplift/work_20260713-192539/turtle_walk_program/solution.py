def turtle(prog: str) -> tuple:
    def process_command(command: str):
        if not command or not command[0].isdigit():
            raise ValueError('bad command')
        
        count_str = ''
        for i in range(len(command)):
            if command[i] == 'F':
                nonlocal x, y, heading
                move(command[:i])
            elif command[i] == 'B':
                nonlocal x, y, heading
                backward(command[:i])
            elif command[i] == 'L':
                turn_left(command[:i])
            elif command[i] == 'R':
                turn_right(command[:i])
            else:
                raise ValueError('bad command')
        
        if count_str and not (len(command) - len(count_str) == 1):
            if command[-2].isdigit() or command[-2] in ['L', 'R']:
                return
            raise ValueError('dangling count')
        
        if command and not command.endswith('F'):
            if i != len(command) - 1:
                raise ValueError('bad command')
            return
        
    x, y, heading = 0, 0, 'N'

    for i in range(len(prog)):
        if prog[i].isdigit() or (prog[i] == 'L' and not count_str):
            count_str += prog[i]
        elif count_str:
            if int(count_str) > 9 or (int(count_str[0]) == 0 and len(count_str) != 1):
                raise ValueError('bad count')
            process_command(count_str)
            count_str = ''
        else:
            process_command(prog[i])
    
    return x, y, heading
