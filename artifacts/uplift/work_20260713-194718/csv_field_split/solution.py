def split_csv_line(line: str) -> list[str]:
    def parse_field(fields, start):
        i = start
        while i < len(line):
            ch = line[i]
            if ch == ',' and (i == start or not (line[i-1].isalpha() and not line[i-1].isspace())) and fields:
                return fields, i + 1
            elif ch == '"':
                new_fields, end = _parse_quoted_field(fields, i)
                return new_fields, end
            elif ch.isspace():
                if fields and (i == start or not (line[i-1].isalpha() and not line[i-1].isspace())):
                    break
                else:
                    while i < len(line) and line[i].isspace(): 
                        i += 1
                    return fields, i
            elif ch == ',' and (i == start or (not (line[i-1].isalpha() and not line[i-1].isspace()))):
                return fields, i + 1
            else:
                i += 1

    def _parse_quoted_field(fields, start):
        quote_escape = False
        escape_count = 0
        for i in range(start, len(line)):
            ch = line[i]
            if not quote_escape and (ch == '"' or escape_count > 0):
                if ch == '"':
                    if escape_count:
                        escape_count -= 1
                    else:
                        return fields + [line[start:i+1][1:-1]], i + 1
                elif ch == ',' and line[i-1] != '\\':
                    break
                else:
                    escape_count = 2 if ch == '"' else 0
            quote_escape = not (quote_escape and ch == '"')
        raise ValueError("Unterminated quoted field")

    fields, _ = parse_field([], 0)
    return fields
