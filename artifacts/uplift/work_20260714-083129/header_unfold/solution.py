def unfold_headers(lines: list[str]) -> list[tuple[str, str]]:
    if not lines:
        return []
    
    if not any(line.startswith(' ') or line.startswith('\t') for line in lines):
        raise ValueError("The first line cannot be a continuation.")
    
    headers = {}
    last_line = None
    result = []
    
    for index, line in enumerate(lines):
        stripped_line = line.strip()
        
        if not (last_line and (stripped_line.startswith(' ') or stripped_line.startswith('\t'))):
            name = ""
            value = ""
            
            colon_index = stripped_line.find(':')
            if colon_index == -1:
                raise ValueError(f"Missing colon in header '{line}'")
            
            name_start, name_end = 0, colon_index
            while name_start < name_end and not lines[index][name_start].isalpha():
                name_start += 1
            
            name = stripped_line[name_start:name_end].lower()
            
            if index == 0:
                last_line = line
            else:
                if name in headers:
                    raise ValueError(f"Duplicate header '{name}'")
                
                for prev_line in reversed(result):
                    if prev_line[0] == name:
                        value = " ".join([headers[name], prev_line[1]])
                        
                        if lines[index - 1].strip() and not line.strip():
                            last_line = None
                            break
                    
                    # Find the previous non-empty header with this name.
                    if len(headers[name]) == len(value):
                        headers[name] += value
                        break
                
                else:
                    headers.setdefault(name, "")
                
                value_start, value_end = colon_index + 1, len(stripped_line)
                while not lines[index][value_end - 1].isalpha():
                    value_end -= 1
                if index == 0 and last_line is None:
                    continue
                
                headers[name] += " ".join([headers[name], stripped_line[colon_index+1:value_end]])
            result.append((name, ''.join(headers[name])))
        else:
            if not all(line.strip() for line in lines[index-1:index+2]):
                raise ValueError("Continuation lines must contain non-whitespace characters.")
            
            headers.setdefault(name.lower(), "").strip()
            value = " ".join([headers[name], stripped_line])
            last_line = line
            
            # Check the continuation's correctness
            if not all(line.strip() for line in [lines[index - 2], stripped_line, lines[index]]):
                raise ValueError("Continuation lines must contain non-whitespace characters.")
            
            # Ensure no trailing whitespace on previous headers
            prev_header_value = result[-1][1] or ""
            if len(prev_header_value) + 1 != len(headers[name]):
                raise ValueError("Trailing spaces in continuation are not allowed.")
        
    return [(name, value) for name, value in sorted(result)]
