def tokenize_quoted(s):
    tokens = []
    buf = []
    started = False
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == ' ' or ch == '\t':
            if started:
                tokens.append(''.join(buf))
                buf = []
                started = False
            i += 1
        elif ch == "'":
            started = True
            i += 1
            j = s.find("'", i)
            if j == -1:
                raise ValueError("unterminated single quote")
            buf.append(s[i:j])
            i = j + 1
        elif ch == '"':
            started = True
            i += 1
            closed = False
            while i < n:
                c = s[i]
                if c == '"':
                    i += 1
                    closed = True
                    break
                if c == '\\':
                    if i + 1 >= n:
                        raise ValueError("unterminated double quote")
                    nxt = s[i + 1]
                    if nxt == '"' or nxt == '\\':
                        buf.append(nxt)
                        i += 2
                    else:
                        raise ValueError("invalid escape in double quotes")
                else:
                    buf.append(c)
                    i += 1
            if not closed:
                raise ValueError("unterminated double quote")
        elif ch == '\\':
            if i + 1 >= n:
                raise ValueError("trailing backslash")
            started = True
            buf.append(s[i + 1])
            i += 2
        else:
            started = True
            buf.append(ch)
            i += 1
    if started:
        tokens.append(''.join(buf))
    return tokens
