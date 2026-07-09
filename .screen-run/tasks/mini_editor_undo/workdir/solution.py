def edit(commands):
    def parse_count(arg):
        if arg == "" or any(c not in "0123456789" for c in arg):
            raise ValueError("bad count")
        n = int(arg)
        if n == 0:
            raise ValueError("bad count")
        return n

    buf = ""
    cur = 0
    undo_stack = []
    for cmd in commands:
        if cmd == "undo":
            if undo_stack:
                buf, cur = undo_stack.pop()
            continue
        sep = cmd.find(" ")
        if sep == -1:
            raise ValueError("bad command")
        verb, arg = cmd[:sep], cmd[sep + 1:]
        if verb == "type":
            if arg == "":
                raise ValueError("bad command")
            undo_stack.append((buf, cur))
            buf = buf[:cur] + arg + buf[cur:]
            cur += len(arg)
        elif verb == "left":
            cur = max(0, cur - parse_count(arg))
        elif verb == "right":
            cur = min(len(buf), cur + parse_count(arg))
        elif verb == "backspace":
            k = min(parse_count(arg), cur)
            if k > 0:
                undo_stack.append((buf, cur))
                buf = buf[:cur - k] + buf[cur:]
                cur -= k
        else:
            raise ValueError("bad command")
    return (buf, cur)
