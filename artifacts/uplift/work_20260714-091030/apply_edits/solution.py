def apply_edits(items, ops):
    out = list(items)
    for iop in ops:
        if not isinstance(iop, tuple):
            raise ValueError()
        op = iop[0]
        if op == "insert":
            if len(iop) != 3 or not (isinstance(iop[1], int) and hasattr(iop[2], '__len__')):
                raise ValueError()
            n, idx, value = iop
            cur = list(out)
            if idx < 0: idx += len(cur)
            if not (0 <= idx <= len(cur)):
                raise IndexError()
            out = cur[:idx] + [value] + cur[idx:]
        elif op == "delete":
            if len(iop) != 2 or not isinstance(iop[1], int):
                raise ValueError()
            n, idx = iop
            cur = list(out)
            if idx < 0: idx += len(cur)
            if not (0 <= idx < len(cur)):
                raise IndexError()
            out = cur[:idx] + cur[idx+1:]
        elif op == "replace":
            if len(iop) != 3 or not isinstance(iop[1], int):
                raise ValueError()
            n, idx, value = iop
            cur = list(out)
            if idx < 0: idx += len(cur)
            if not (0 <= idx < len(cur)):
                raise IndexError()
            out = cur[:idx] + [value] + cur[idx+1:]
        else:
            raise ValueError()
    return out
