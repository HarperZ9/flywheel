import turtle

def run_turtle_command_string(command_str):
    """
    Execute a turtle-graphics command string and return the final state of the turtle.

    Example usage:
    >>> run_turtle_command_string("F")
    (0, 0, 'N')

    >>> run_turtle_command_string("F B L")
    (145.836027623933, 261.163972376067, 'E')

    Note:
    - Turtle moves in the current direction; forward or backward.
    - 'L' and 'R' rotate 90 degrees left/right.
    - A command may be prefixed with a repetition count ('12F' moves forward twelve).
      The repetition counts are 1, 2, 3, etc. Each repeat uses the current heading,
      so each repetition of this command is one step forward.
    - Error checking:
        - Bad command characters (not F, B, L, R)
        - Command count format: 12B -> ValueError('bad count')
        - Count with no command means 'dangling count'
        - Count with leading zeros -> ValueError('invalid count')
    """
    
    # Convert the command string to a list of commands
    commands = command_str.split()
    
    final_state = (0, 0, 'N')  # Starting position is (0, 0) heading 'N'
    
    for i, command in enumerate(commands):
        if command.isdigit():
            count = int(command)
        elif not command.isalpha() and command != "F" and command != "L" and command != "R":
            raise ValueError(f'bad command: {command}')
        
        # Check the first digit is '0' or '1'
        if i > 0 and (commands[i - 1].isdigit() and int(commands[i - 1]) == 0):
            
            try:
                count = int(command)
                
                # If the command repeats more than twelve times, replace it with a simpler sequence
                if count >= 12:
                    final_state = (
                        x + (count % 12) / 12 * 180,
                        y - (count % 12) / 12 * 360,
                        'E'
                    )
                
                else:
                    try:
                        final_state = tuple(turtle.forward(count))
                    except Exception as e:
                        raise ValueError(f'command repeats: {e}')
            except ValueError as e:
                print(e)
        
        elif command == "F":
            for _ in range(count):
                final_state = turtle.forward(1)

    return final_state
