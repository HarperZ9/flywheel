def outline_number(lines):
    if not all(isinstance(line, str) for line in lines):
        raise ValueError('bad input')
    
    def is_header(line):
        if len(line) == 0 or line[0] != '#':
            return False
        hash_count = line.count('#', 0, 1)
        if hash_count < 1 or hash_count > 6:
            return False
        title = line.strip()
        return len(title) > 0 and title[0] != ' '
    
    counter = [0] * 7
    
    for line in lines:
        if not is_header(line):
            continue
        
        level = line.count('#', 0, 1)
        if any(c >= i for i, c in enumerate(counter[:level])):
            raise ValueError('bad nesting')
        
        for i in range(1, level + 1):
            counter[i] = counter[i - 1] + 1
            if i == level:
                break
        
        header_number = '.'.join(str(c) for c in counter[1:level+1])
        result_line = f"{header_number} {line.lstrip('#').strip()}"
        lines[lines.index(line)] = result_line
    
    return [line for line in lines if is_header(line)]
