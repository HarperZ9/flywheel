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
        name = raw.lstrip()
        if "/" in name:
            raise ValueError("slash in name")
        level = _level(raw)
        if last_level is None:
            if level != 0:
                raise ValueError("indent jump")
        else:
            if level - last_level > 1:
                raise ValueError("indent jump")
            while stack and stack[-1][2] >= level:
                stack.pop()
        if len(stack) == level:
            path = name
        else:
            path = "/".join(n for _, n, _ in stack[:level]) + "/" + name
        stack.append((line, name, level))
        last_level = level
        # Check if this is a leaf: next non-blank line must have equal or deeper indent
        is_leaf = True
        for j in range(i + 1, len(lines)):
            test = lines[j].strip()
            if test:
                if _level(lines[j]) > level:
                    break
                is_leaf = False
                break
        else:
            is_leaf = True
        if is_leaf:
            leaf_paths.append(path)
    return leaf_paths
