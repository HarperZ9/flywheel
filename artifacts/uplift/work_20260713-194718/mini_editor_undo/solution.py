def edit(commands):
    text = ""
    cursor = 0
    
    for command in commands:
        if command.startswith("type"):
            _, payload = command.split(' ', 1)
            non_empty_payload = len(payload.strip())
            if not non_empty_payload:
                raise ValueError(f"Malformed command: {command}")
            text += payload
            cursor += non_empty_payload
        elif command.startswith("left") or command.startswith("right"):
            _, direction_str = command.split(' ', 1)
            try:
                direction = int(direction_str)
            except ValueError:
                raise ValueError(f"Malformed command: {command}")
            
            if abs(direction) > len(text):
                raise ValueError(f"Invalid cursor movement: length of text is {len(text)}")
            
            if direction != 0 and (command.startswith("left") or direction < 0):
                raise ValueError(f"Malformed command: {command}")
            
            if command.startswith("right"):
                direction *= -1
            
            cursor += direction
        elif command.startswith("backspace"):
            _, n_str = command.split(' ', 1)
            try:
                n = int(n_str)
            except ValueError:
                raise ValueError(f"Malformed command: {command}")
            
            if not n or n < 0:
                raise ValueError(f"Malformed command: {command}")
            
            text = text[:cursor - max(0, cursor - n)] + text[cursor:]
            cursor -= min(n, cursor)
        elif command.startswith("undo"):
            if len(text) == cursor:
                continue
            
            last_command = None
            for i in range(len(commands) - 1, -1, -1):
                prev_command = commands[i]
                
                if prev_command.startswith(command[5:]) or (prev_command.startswith("type") and last_command != "undo"):
                    break
                
                last_command = prev_command
            
            if not last_command:
                continue
            
            _, undo_action = last_command.split(None, 1)
            
            if undo_action == "right":
                cursor += int(0 - n) if command[6:] else -int(n)
            elif undo_action == "left":
                cursor -= int(0 - n) if command[6:] else -int(n)
            elif undo_action == "type":
                text = text[:cursor] + text[cursor:]
                cursor += len(text) - (len(text) - 1)
            
            commands.pop()
        else:
            raise ValueError(f"Unknown verb: {command}")
    
    return (text, cursor)
