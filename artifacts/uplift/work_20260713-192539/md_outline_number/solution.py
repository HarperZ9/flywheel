def outline_number(lines):
    if not all(isinstance(line, str) for line in lines):
        raise ValueError('bad input')
    
    header_stack = []
    headers = []
    level_counters = {k: 0 for k in range(1, 7)}

    for i, line in enumerate(lines):
        if not line or not line[0] == '#':
            continue

        hash_count = line.count('#')

        if not (hash_count > 0 and hash_count < 7) or any(line[i+2] != ' ' for i in range(hash_count - 1)):
            raise ValueError('bad header')
        
        title = line[hash_count:line.find(' ', hash_count)]
        level = hash_count
        level_counters[level] += 1

        if len(header_stack) > 0 and level < header_stack[-1][0]:
            raise ValueError('bad nesting')

        header_text = '.'.join(f'{i+level:0{level}}' for i in range(level-1)) + ' ' + title
        headers.append(header_text)
        header_stack.append((level, level_counters))

    return headers
