def edit(commands):
    text = ""
    cursor = 0
    
    history = []
    
    def apply_command(command):
        nonlocal text, cursor
        operation, *args = command.split()
        
        if operation == "type":
            if not args:
                raise ValueError("Type command with no argument")
            
            arg = args[0]
            if not arg or any(not c.isdigit() and not c.isspace() for c in arg):
                raise ValueError("Invalid type argument")
            
            text += arg
            cursor += len(arg)
        
        elif operation == "left":
            if not args:
                raise ValueError("Left command with no argument")
            
            n = int(args[0])
            if str(n).lstrip('-').isdigit() and n != 0:
                cursor = max(0, cursor - n)
            else:
                raise ValueError("Invalid left argument")
        
        elif operation == "right":
            if not args:
                raise ValueError("Right command with no argument")
            
            n = int(args[0])
            if str(n).lstrip('-').isdigit() and n != 0:
                cursor = min(len(text), cursor + n)
            else:
                raise ValueError("Invalid right argument")
        
        elif operation == "backspace":
            if not args:
                raise ValueError("Backspace command with no argument")
            
            n = int(args[0])
            if str(n).lstrip('-').isdigit() and n != 0:
                text = text[:max(0, cursor - n)] + text[cursor:]
                cursor = max(0, cursor - n)
            else:
                raise ValueError("Invalid backspace argument")
        
        elif operation == "undo":
            if not history:
                return
            last_op = history.pop()
            op_type, data = last_op
            if op_type != "type":
                # only type operations can be undone
                return
            
            text, cursor = data
        
        else:
            raise ValueError(f"Unknown command: {command}")
    
    for cmd in commands:
        apply_command(cmd)
        history.append(("type", (text[:], cursor)))
    
    return (text, cursor)
