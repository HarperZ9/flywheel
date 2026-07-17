def outline_number(lines):
    if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
        raise ValueError('bad input')
    counters = [0] * 6
    last_level = 0
    out = []
    for line in lines:
        if not line.startswith('#'):
            continue
        n = len(line)
        i = 0
        while i < n and line[i] == '#':
            i += 1
        if (i > 6 or i < 1 or
                i >= n or line[i] != ' ' or
                i + 1 < n and line[i + 1] == ' '):
            raise ValueError('bad header')
        level = i
        title = line[i + 1:]
        if last_level != 0:
            if level > last_level + 1:
                raise ValueError('bad nesting')
            for d in range(last_level, level - 1, -1):
                counters[d] = 0
        counters[level - 1] += 1
        out.append(f"{'.'.join(str(counters[d]) for d in range(level))} {title}")
        last_level = level
    return out
