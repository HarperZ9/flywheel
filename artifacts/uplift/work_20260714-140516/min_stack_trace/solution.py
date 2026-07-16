from __future__ import annotations

def min_stack(ops) -> list[int | None]:
    if not isinstance(ops, list):
        raise ValueError("bad ops")
    out: list = []
    stack: list = []
    mins: list = []  # ordered by decreasing size; all values are present at their push time
    for o in ops:
        if isinstance(o, tuple) and len(o) == 2:
            cmd, v = o
            if cmd != "push" or not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("bad op")
            stack.append(v)
            mins.append(v if not mins else min(v, mins[-1]))
        elif o in ((), tuple()):
            raise ValueError("bad op")
        elif isinstance(o, tuple) and len(o) == 1:
            cmd = o[0]
            if cmd == "pop":
                if not stack:
                    raise ValueError("empty stack")
                out.append(stack.pop())
                mins.pop()
            elif cmd == "top":
                if not stack:
                    raise ValueError("empty stack")
                out.append(stack[-1])
            elif cmd == "min":
                if not mins:
                    raise ValueError("empty stack")
                out.append(mins[-1])
            else:
                raise ValueError("bad op")
        else:
            raise ValueError("bad op")
    return out
