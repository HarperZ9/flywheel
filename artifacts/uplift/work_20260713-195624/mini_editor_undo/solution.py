def edit(commands):
    text = ""
    cursor = 0

    for command in commands:
        if command.startswith("type"):
            _, payload = command.split(",", 1)
            if "_" in payload or " " in payload or "\n" in payload:
                raise ValueError(f"Malformed type command: '{command}'")
            if len(payload) == 0:
                raise ValueError(f"Malformed type command: '{}'")

        elif command.startswith("left"):
            _, n = command.split(",", 1)
            try:
                text, cursor = left(n, text, cursor)
            except ValueError as e:
                print(e)

        elif command.startswith("right"):
            _, n = command.split(",", 1)
            try:
                text, cursor = right(n, text, cursor)
            except ValueError as e:
                print(e)

        elif command.startswith("backspace"):
            _, n = command.split(",", 1)
            try:
                text, cursor = backspace(n, text, cursor)
            except ValueError as e:
                print(e)

        elif command.startswith("undo") or (command.replace(" ", "").isdigit()):
            if command == "undo":
                raise ValueError(f"undo target is not possible without a non-duplicate command")
            if len(command) > 1 and int(command[1:]) < 0:
                print("undo cannot be undone with negative numbers")
                continue

            try:
                text, cursor = undo(command, text, cursor)
            except ValueError as e:
                print(e)

        else:
            raise ValueError(f"Unknown command: '{command}'")

    return (text, cursor)
