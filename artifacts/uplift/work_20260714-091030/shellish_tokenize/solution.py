def tokenize_quoted(s: str) -> list[str]:
    out = []
    buf = []
    in_double = False
    in_single = False
    chars = iter(s)
    n = len(s)

    def flush():
        if buf:
            out.append("".join(buf))
            del buf[:]

    i = 0
    while i < n:
        c = s[i]
        i += 1
        if in_double:
            if c == '"':
                flush()
                in_double = False
                continue
            elif c == "\\":
                # consume escape sequence
                if i >= n:
                    raise ValueError("unterminated quoted segment")
                next_c = s[i]
                i += 1
                if next_c == '"':
                    buf.append('"')
                elif next_c == "\\":
                    buf.append("\\")
                else:
                    raise ValueError(f"invalid escape: \\{next_c}")
            else:
                buf.append(c)
        elif in_single:
            if c == "'":
                flush()
                in_single = False
                continue
            else:
                buf.append(c)
        else:
            if c == "\\":
                if i >= n:
                    raise ValueError("backslash at end of input")
                next_c = s[i]
                i += 1
                buf.append(next_c)
                continue
            elif c == '"':
                flush()
                in_double = True
            elif c == "'":
                flush()
                in_single = True
            elif c.isspace():
                if buf:
                    flush()
            else:
                buf.append(c)

    if in_double or in_single:
        raise ValueError("unterminated quoted segment")

    flush()
    return out
