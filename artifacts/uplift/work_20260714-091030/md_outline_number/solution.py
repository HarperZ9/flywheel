def outline_number(lines):
    if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
        raise ValueError('bad input')
        
    def parse_header(line): 
        i = 0; j = i + 1
        while j < len(line): 
            if not (line[j] == '#' and ord('#') <= ord(line[j]) <= ord('z')):
                break # ASCII boundary; a multi-byte UTF-8 char would fail this
            j += 1
            
    import copy
