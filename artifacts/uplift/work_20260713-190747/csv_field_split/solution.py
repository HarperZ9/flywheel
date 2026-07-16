def split_csv_line(line: str) -> list[str]:
    fields = []
    i = 0
    n = len(line)
    
    while i < n:
        if line[i] == ',':
            fields.append(line[i:i+1])
            i += 1
        elif line[i] == '"':
            j = i + 1
            while j < n and (line[j] != '"' or (j > i + 1 and line[j-2:j] == '""')):
                if line[j:j+2] == '""':
                    fields.append('"' * 2)
                    j += 1
                else:
                    fields.append(line[j])
                j += 1
            if j == n or line[j] != ',':
                raise ValueError("Unterminated quoted field")
            fields.append(line[j])
            i = j + 1
        else:
            j = i + 1
            while j < n and line[j] not in (',', '"'):
                j += 1
            fields.append(line[i:j])
            i = j
            
    if i != n:
        raise ValueError("Extra characters after valid fields")
    
    return fields
