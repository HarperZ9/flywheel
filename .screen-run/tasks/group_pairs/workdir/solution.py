def group_pairs(pairs):
    for p in pairs:
        if type(p) is not tuple or len(p) != 2:
            raise ValueError("malformed pair")
    out = {}
    for k, v in pairs:
        if k in out:
            out[k].append(v)
        else:
            out[k] = [v]
    return out
