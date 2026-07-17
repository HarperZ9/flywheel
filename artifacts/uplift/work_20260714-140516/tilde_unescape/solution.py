def untilde(s: str) -> str:
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "~":
            if i == n - 1:
                raise ValueError("dangling escape")
            if s[i + 1] == "~":
                out.append("~")
                i += 2
                continue
            if s[i + 1] in ("n", "t"):
                out.append("\n" if s[i + 1] == "n" else "\t")
                i += 2
                continue
            if s[i + 1] == "x":
                if i + 3 > n:
                    raise ValueError("bad hex")
                if any(not c in "0123456789abcdefABCDEF" for c in s[i + 2 : i + 4]):
                    raise ValueError("bad hex")
                out.append(chr(int(s[i + 2 : i + 4], 16)))
                i += 4
                continue
            if s[i + 1] in ("N", "T", "X"):
                raise ValueError("bad escape")
            # ~ + a non-~nxt character; keep the two characters literally, because
            # a bare ~ on its own is otherwise never possible (there's always an
            # ~ after it) and so this must be a corrupt input trying to make us read
            # it anyway.
            out.append(c)
            i += 1
            continue

        if ord(c) < 32:
            raise ValueError("raw control")
        out.append(c)
        i += 1
    return "".join(out)
