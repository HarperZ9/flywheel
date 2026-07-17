def outline_paths(lines):
    def _level(line):
        if "\t" in line:
            raise ValueError("tab in indent")
        n = len(line) - len(line.lstrip())
        if n % 2 != 0:
            raise ValueError("odd indent")
        return n // 2

    stack = []
    leaf_paths = []
    last_level = None
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        name = line.lstrip()
        if "/" in name:
            raise ValueError("slash in name")
        level = _level(raw)
        if last_level is not None and level > last_level + 1:
            raise ValueError("indent jump")
        while stack and len(stack[-1]) == level:
            stack.pop()
        stack.append(name)
        if i + 1 < len(lines) and _level(lines[i + 1].strip() or lines[i + 1]) <= level:
            continue
        leaf_paths.append("/".join(stack))
    return leaf_paths
