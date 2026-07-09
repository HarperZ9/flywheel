def apply_edits(items, ops):
    def norm(i, n, upper):
        j = i + n if i < 0 else i
        if j < 0 or j > upper:
            raise IndexError("index out of range")
        return j

    out = list(items)
    for op in ops:
        if not isinstance(op, tuple) or not op:
            raise ValueError("malformed op")
        name = op[0]
        if name == "insert":
            if len(op) != 3:
                raise ValueError("malformed op")
            j = norm(op[1], len(out), len(out))
            out.insert(j, op[2])
        elif name == "delete":
            if len(op) != 2:
                raise ValueError("malformed op")
            j = norm(op[1], len(out), len(out) - 1)
            del out[j]
        elif name == "replace":
            if len(op) != 3:
                raise ValueError("malformed op")
            j = norm(op[1], len(out), len(out) - 1)
            out[j] = op[2]
        else:
            raise ValueError("unknown op")
    return out
