def untilde(s):
    hexd = "0123456789abcdefABCDEF"
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "~":
            if i + 1 >= len(s):
                raise ValueError("dangling escape")
            e = s[i + 1]
            if e == "~":
                out.append("~")
                i += 2
            elif e == "n":
                out.append("\n")
                i += 2
            elif e == "t":
                out.append("\t")
                i += 2
            elif e == "x":
                h = s[i + 2:i + 4]
                if len(h) < 2 or h[0] not in hexd or h[1] not in hexd:
                    raise ValueError("bad hex")
                out.append(chr(int(h, 16)))
                i += 4
            else:
                raise ValueError("bad escape")
        else:
            if ord(c) < 32:
                raise ValueError("raw control")
            out.append(c)
            i += 1
    return "".join(out)
