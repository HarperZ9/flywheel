def natural_compare(a: str, b: str) -> int:
    def runs(s):
        out = []
        i = 0
        while i < len(s):
            if s[i].isdigit():
                j = i + 1
                while j < len(s) and s[j].isdigit():
                    j += 1
                out.append(int(s[i:j]))
                i = j
            else:
                j = i + 1
                while j < len(s) and not s[j].isdigit():
                    j += 1
                out.append(s[i:j])
                i = j
        return tuple(out)

    a_runs = runs(a)
    b_runs = runs(b)
    la, lb = len(a_runs), len(b_runs)
    for i in range(min(la, lb)):
        va, vb = a_runs[i], b_runs[i]
        if isinstance(va, str) and isinstance(vb, int):
            return -1
        if isinstance(vb, str) and isinstance(va, int):
            return 1
        if isinstance(va, int) and isinstance(vb, int):
            if va < vb:
                return -1
            if va > vb:
                return 1
            continue
        assert isinstance(va, str) and isinstance(vb, str)
        d = (va > vb) - (va < vb)
        if d != 0:
            return d
    if la < lb:
        return -1
    if la > lb:
        return 1
    return 0
