def merge_tallies(a, b):
    def check(v):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("count must be int, not bool/other")

    for v in a.values():
        check(v)
    for v in b.values():
        check(v)
    out = {}
    for k, v in a.items():
        total = v + b.get(k, 0)
        if total != 0:
            out[k] = total
    for k, v in b.items():
        if k not in a and v != 0:
            out[k] = v
    return out
