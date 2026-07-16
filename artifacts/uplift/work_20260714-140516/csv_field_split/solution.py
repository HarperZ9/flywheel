def split_csv_line(line: str) -> list[str]:
    fields = []
    pos = 0
    n = len(line)
    while pos < n:
        if line[pos] == '"':
            # Quoted field. Must start with a quote - check this explicitly so the
            # generic quoted-field parsing cannot silently treat a leading " as
            # starting an empty string before the real data.
            pos += 1
            buf = []
            while pos < n:
                ch = line[pos]
                if ch == '"':
                    # Double-quote escape: "" -> one "
                    if pos + 1 < n and line[pos+1] == '"':
                        buf.append('"')
                        pos += 2
                    elif line[pos+1] in (',', '\0'):  # end of quoted string
                        fields.append("".join(buf))
                        pos += 1
                        if pos >= n or line[pos] == ',':
                            pos += 1
                        break
                    else:
                        raise ValueError(f"quoted field closes with unexpected character: {line!r}")
                else:
                    buf.append(ch)
                    pos += 1
            continue

        # Unquoted field. Comma separates fields; anything quoted is an error.
        start = pos
        while pos < n and line[pos] != ',':
            if line[pos] == '"':
                raise ValueError(f"unquoted field contains embedded quote: {line!r}")
            pos += 1
        fields.append(line[start:pos])
        if pos < n:
            pos += 1

    return fields
