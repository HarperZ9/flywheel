def edit(commands):
    from collections.abc import Sequence

    def _is_not_empty_str_of_ascii_digits(value: str) -> bool:
        return isinstance(value, str) and value and str.isascii(value) and all(char in "0123456789" for char in value)

    if not isinstance(commands, Sequence):
        raise ValueError("commands must be a list or tuple")
    buffer = []
    cursor = 0
    undone: list[tuple[list[str], int]] = []
    recorded_text: list[str] = []
    recorded_cursor: list[int] = []

    def _record():
        if "".join(buffer) != "".join(recorded_text) or cursor != recorded_cursor[-1]:
            recorded_text[:] = buffer[:]
            recorded_cursor.append(cursor)
            undone.clear()

    for command in commands:
        if not isinstance(command, str):
            raise ValueError("commands must contain only strings")
        parts = command.split(None, 1)
        if len(parts) < 2:
            raise ValueError(f"malformed command: {command}")
        verb, value = parts
        if verb == "type":
            if not _is_not_empty_str_of_ascii_digits(value):
                raise ValueError(f"type payload must be a non-empty string of ASCII digits, got {value!r}")
            _record()
            buffer[cursor : cursor] = list(value)
            cursor += len(value)
        elif verb in ("left", "right"):
            if not _is_not_empty_str_of_ascii_digits(value):
                raise ValueError(f"{verb} requires a non-empty numeric payload; got {value!r}")
            steps = int(value)
            if not steps:
                raise ValueError(f"{verb} steps must be nonzero; got {steps:d}")
            _record()
            if verb == "left":
                cursor = max(0, cursor - steps)
            else:
                cursor = min(len(buffer), cursor + steps)
        elif verb == "backspace":
            if not _is_not_empty_str_of_ascii_digits(value):
                raise ValueError(f"{verb} requires a non-empty numeric payload; got {value!r}")
            count = int(value)
            if not count:
                raise ValueError(f"{verb} count must be nonzero; got {count:d}")
            _record()
            to_delete = min(cursor, count)
            del buffer[cursor - to_delete : cursor]
            cursor -= to_delete
        elif verb == "undo":
            if value != "":
                raise ValueError(f"undo takes no argument; got {value!r}")
            if recorded_text:
                buffer[:] = recorded_text[:]
                cursor = recorded_cursor.pop()
                undone.append((recorded_text, cursor))
                recorded_text.clear()
            continue
        else:
            raise ValueError(f"unknown command verb: {verb!r}")

    return "".join(buffer), cursor
