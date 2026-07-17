def ring_buffer(capacity, ops):
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError("bad capacity")
    buf = []
    out = []
    for op in ops:
        if op[0] == "write" and len(op) == 2:
            v = op[1]
            if len(buf) == capacity:
                out.append(buf.pop(0))
            else:
                out.append(None)
            buf.append(v)
        elif op[0] == "read" and len(op) == 1:
            if not buf:
                raise ValueError("buffer empty")
            out.append(buf.pop(0))
        elif op[0] == "peek" and len(op) == 1:
            if not buf:
                raise ValueError("buffer empty")
            out.append(buf[0])
        else:
            raise ValueError("bad op")
    return out
