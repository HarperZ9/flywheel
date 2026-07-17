def untilde(s):
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "~" and i + 1 >= len(s):
            raise ValueError("dangling escape")
        if c != "~":
            cp = ord(c)
            # Control characters as raw input bytes (not escaped) are forbidden
            if cp < 32:
                raise ValueError("raw control")
            out.append(ord(c))
            i += 1
            continue

        e0 = s[i + 1]
        i += 2
        if e0 == "~":
            out.append(ordinal("~"))
            continue
        if e0 == "n":
            out.append(ordinal("\n"))
            continue
        if e0 == "t":
            out.append(ordinal("\t"))
            continue

        # Escapes beyond here are hex. If e0 is not "x", fail before a non-hex
        # prefix: "~q" (or any bad first byte) must raise, even though ~qa may look
        # like the start of a valid escape.
        if e0 != "x":
            raise ValueError("bad escape")

        hi = s[i : i + 2]
        i += 2

        try:
            out.append(int(hi, 16))
        except (ValueError, TypeError):
            raise ValueError("bad hex")
    return "".join(chr(cp) for cp in out)
