def outline_number(lines):
    if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
        raise ValueError('bad input')
    counters = [0] * 6
    last_level = 0
    out = []
    for line in lines:
        if not line.startswith('#'):
            continue
        hash_count = 0
        while hash_count < len(line) and line[hash_count] == '#':
            hash_count += 1
        if (hash_count > 6 or hash_count <= 0
                or hash_count != len(line[:hash_count])
                or not line[hash_count:].startswith(' ')):
            raise ValueError('bad header')
        title = line[hash_count + 1:]
        if (not title or title[0] == ' '
                or any(ch.isspace() and ch == title[i - 1]
                       for i, ch in enumerate(title) if i > 0)):
            raise ValueError('bad header')
        level = hash_count - 1
        if last_level < level:
            raise ValueError('bad nesting')
        counters[level] += 1
        for d in range(level + 1, 6):
            counters[d] = 0
        out.append(('.'.join(str(counters[i]) for i in range(hash_count))
                    + ' ' + title).strip())
    return out
