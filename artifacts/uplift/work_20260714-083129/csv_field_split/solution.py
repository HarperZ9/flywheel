def split_csv_line(line: str) -> list[str]:
    fields = []
    depth = 0
    i = 0

    while i < len(line):
        if line[i] == ',' and not depth:
            # Normal comma with no escaping or quoted content - add an empty field.
            fields.append("")
            i += 1
            continue
        
        if (line[i] == '"' and depth % 2 == 0) or (i == 0 and line[i] == ','):
            depth += 1
            i += 1

            while i < len(line) and (line[i] != '"') or (depth % 2 and line[i-1:i+1] != '""'):
                if line[i] == '\\':
                    i += 1
                i += 1
        
            depth -= 1
    
        else:
            start = i
            while i < len(line) and not (line[i] == ',' or line[i] == '"'):
                i += 1
            
            fields.append(line[start:i])
        
    if depth > 0:
        raise ValueError('Unterminated quoted field')
    
    return fields
