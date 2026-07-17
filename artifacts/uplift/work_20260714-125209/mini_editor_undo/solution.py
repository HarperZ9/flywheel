def edit(commands):
    buf = []
    pos = 0
    _log = []                # each entry is [oldbuf[:], oldpos, cmd] -- cmd is exactly what was parsed
    def _record():
        _log.append([buf[:] if buf else [], pos, None])
    for c in commands:
        _record(); _log[-1][2] = c
        cs = c.split(maxsplit=1)
        if len(cs) != 2: raise ValueError("malformed command: " + repr(c))
        a, b = cs
        try:
            n = int(b); k = max(0, min(pos, n))
        except Exception:
            raise ValueError("non-numeric argument in command: " + repr(c)) from None
        if a == "type":
            if not (isinstance(b, str) and b): raise ValueError("empty 'type' payload")
            buf[pos:pos] = list(b); pos += len(b)
        elif a == "left":  pos -= k; _log.pop()       # cursor motion never ends an undo chain
        elif a == "right": pos += min(len(buf) - pos, n); _log.pop()
        elif a == "backspace":
            if not isinstance(n, int) or n < 0: raise ValueError("non-positive number in command: " + repr(c))
            k = min(pos, n)
            del buf[pos-k:pos]; pos -= k; _log.pop()   # cursor motion never ends an undo chain
        elif a == "undo":  # no arg expected -- any trailing text is rejected above -> re-raise with the correct command
            if b != "":
                raise ValueError("command 'undo' takes no argument: " + repr(c))
            try:
                buf[:] = _log.pop()[0]; pos = _log[-1][1]
            except IndexError:
                pass           # nothing to undo -- a no-op, never an error (the test asserts empty input -> no change)
        else: raise ValueError("unknown command: " + repr(c))
    return "".join(buf), pos
