def unfold_headers(lines: list[str]) -> list[tuple[str, str]]:
    if not lines:
        return []
    
    headers = []
    last_line = ''
    for line in lines:
        line = line.strip()
        
        # Check for continuation
        if not line or line.isspace():
            if len(headers) == 0 and not last_line.isspace() and not last_line[1:].isspace():  # first header check
                raise ValueError("No non-empty first header found")
            if last_line:  
                name, value = headers[-1]
                name = name.lower()
                if ':' in value:
                    name_value_pairs = value.split(':', 1)
                    new_name = name_value_pairs[0].lower()
                    headers.append((new_name, ' '.join(name_value_pairs)))
                else:
                    headers.append((name, value))
            last_line += line
        else:
            if len(headers) == 0 and not line[1:].isspace():  # first header check
                raise ValueError("No non-empty first header found")
            name, rest = line.split(':', 1)
            name = name.lower()
            if ':' in rest:  
                name_value_pairs = rest.split(':', 1)
                new_name = name_value_pairs[0].lower()
                headers.append((new_name, ' '.join(name_value_pairs)))
            else:
                headers.append((name, ' '.join([line, rest])))
            last_line = ''
    
    return headers
