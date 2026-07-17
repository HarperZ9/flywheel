def ring_buffer(capacity, ops):
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError("bad capacity")
    buffer = []
    out = []
    i = 0
    for op in ops:
        if len(op) == 2 and op[0] == "write":
            v = op[1]
            if len(buffer) >= capacity:
                out.append(buffer[i % capacity])
            else:
                out.append(None)
            buffer.insert(i % capacity, v)
            i += 1
        elif len(op) == 1:
            if op[0] == "read":
                if not buffer:
                    raise ValueError("buffer empty")
                idx = i - len(buffer) + (i % capacity) - 1 if i >= len(buffer) else i % capacity - 1
                out.append(buffer.pop(idx))
            elif op[0] == "peek":
                if not buffer:
                    raise ValueError("buffer empty")
                idx = i - len(buffer) + (i % capacity) - 1 if i >= len(buffer) else i % capacity - 1
                out.append(buffer[idx])
        else:
            raise ValueError("bad op")
    return out
