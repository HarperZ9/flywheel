def edit(commands):
    stack = []
    text = ""
    cursor = 0

    for cmd in commands:
        args = cmd.split(maxsplit=1)
        verb = args[0]

        if verb == "type":
            if len(args) < 2 or not args[1]:
                raise ValueError
            stack.append((text, cursor))
            payload = args[1]
            text = text[:cursor] + payload + text[cursor:]
            cursor += len(payload)
        elif verb in ("left", "right"):
            if len(args) != 2 or not args[1].isdigit() or int(args[1]) <= 0:
                raise ValueError
            n = int(args[1])
            stack.append((text, cursor))
            if verb == "left":
                cursor = max(0, cursor - n)
            else:
                cursor = min(len(text), cursor + n)
        elif verb == "backspace":
            if len(args) != 2 or not args[1].isdigit() or int(args[1]) <= 0:
                raise ValueError
            deletions = min(cursor, int(args[1]))
            stack.append((text, cursor))
            text = text[:cursor - deletions] + text[cursor:]
            cursor -= deletions
        elif verb == "undo":
            if len(args) > 1 or not stack:
                raise ValueError
            text, cursor = stack.pop()
        else:
            raise ValueError

    return (text, cursor)
