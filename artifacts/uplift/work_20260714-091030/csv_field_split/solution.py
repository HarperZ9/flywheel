def split_csv_line(line: str) -> list[str]:
    fields = []
    pos = 0
    n = len(line)

    while pos < n:
        if line[pos] == '"':
            # Quoted field (quote is first character of the field).
            if pos > 0 and line[pos - 1] != ',':
                raise ValueError("double quote inside unquoted field")
            pos += 1
            qfield = ""
            while True:
                if pos >= n:
                    raise ValueError("unterminated quoted field")
                if line[pos] == '"' and (pos + 1 < n and line[pos + 1] == '"'):
                    # Double-quote escape: consumes two characters, appends one.
                    qfield += '"'
                    pos += 2
                elif line[pos] == '"' and (pos + 1 >= n or line[pos + 1] == ','):
                    # Closing quote; must be followed by , or end of string.
                    pos += 1
                    break
                else:
                    qfield += line[pos]
                    pos += 1
            fields.append(qfield)
        elif line[pos] == ',':
            # Empty field (two consecutive commas, or start/end with comma).
            fields.append("")
            pos += 1
        else:
            # Unquoted field starting at this position.
            end = line.find(',', pos)
            if end == -1:
                end = n
            field = line[pos:end]
            for ch in field:
                if ch == '"':
                    raise ValueError("double quote inside unquoted field")
            fields.append(field)
            pos = end

    return fields
