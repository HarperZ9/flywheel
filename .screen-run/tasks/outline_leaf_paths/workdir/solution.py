def outline_paths(lines):
    entries = []
    prev_level = -1
    for line in lines:
        if line.strip() == "":
            continue
        i = 0
        while i < len(line) and line[i] in " \t":
            i += 1
        lead = line[:i]
        if "\t" in lead:
            raise ValueError("tab in indent")
        if len(lead) % 2 != 0:
            raise ValueError("odd indent")
        level = len(lead) // 2
        if level > prev_level + 1:
            raise ValueError("indent jump")
        name = line[i:].rstrip()
        if "/" in name:
            raise ValueError("slash in name")
        entries.append((level, name))
        prev_level = level
    paths = []
    stack = []
    for idx, (level, name) in enumerate(entries):
        del stack[level:]
        stack.append(name)
        next_level = entries[idx + 1][0] if idx + 1 < len(entries) else -1
        if next_level <= level:
            paths.append("/".join(stack))
    return paths
