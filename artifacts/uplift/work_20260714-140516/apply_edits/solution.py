def apply_edits(items, ops):
    result = items.copy()
    n = len(result)
    for op in ops:
        if not isinstance(op, tuple) or len(op) < 2:
            raise ValueError(f"bad operation {op!r}")
        cmd, i0 = op[0], op[1]
        if cmd == "insert":
            if len(op) != 3:
                raise ValueError(f"wrong arity for insert: {op!r}")
            value = op[2]
            i = i0 + n if i0 < 0 else i0
            if not (0 <= i <= n):
                raise IndexError(f"insert index {i} out of range 0..{n}")
            result.insert(i, value)
        elif cmd == "delete":
            if len(op) != 2:
                raise ValueError(f"wrong arity for delete: {op!r}")
            i = i0 + n if i0 < 0 else i0
            if not (0 <= i < n):
                raise IndexError(f"delete index {i} out of range 0..{n-1}")
            del result[i]
        elif cmd == "replace":
            if len(op) != 3:
                raise ValueError(f"wrong arity for replace: {op!r}")
            value = op[2]
            i = i0 + n if i0 < 0 else i0
            if not (0 <= i < n):
                raise IndexError(f"replace index {i} out of range 0..{n-1}")
            result[i] = value
        else:
            raise ValueError(f"unknown operation '{cmd}'")
    return result
