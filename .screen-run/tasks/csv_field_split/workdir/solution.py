def split_csv_line(line):
    fields = []
    buf = []
    i = 0
    n = len(line)
    while True:
        if i < n and line[i] == '"':
            i += 1
            closed = False
            while i < n:
                ch = line[i]
                if ch == '"':
                    if i + 1 < n and line[i + 1] == '"':
                        buf.append('"')
                        i += 2
                    else:
                        i += 1
                        closed = True
                        break
                else:
                    buf.append(ch)
                    i += 1
            if not closed:
                raise ValueError("unterminated quoted field")
            if i < n and line[i] != ',':
                raise ValueError("unexpected character after closing quote")
        else:
            while i < n and line[i] != ',':
                if line[i] == '"':
                    raise ValueError("quote inside unquoted field")
                buf.append(line[i])
                i += 1
        fields.append(''.join(buf))
        buf = []
        if i < n:
            i += 1
        else:
            break
    return fields
