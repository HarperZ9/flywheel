def outline_paths(lines):
    """Convert an indentation-based outline into the list of leaf paths."""
    out = []
    stack = []
    last_level = None

    for line in lines:
        stripped = line.lstrip()
        if not stripped:
            continue  # blank lines are skipped entirely and never participate
                     # in level tracking (RFC grammar rule: skip them)

        indent = len(line) - len(stripped)
        name = stripped.rstrip()

        if "\t" in line[:indent]:
            raise ValueError("tab in indent")
        if indent % 2 != 0:
            raise ValueError("odd indent")
        level = indent // 2

        if "/" in name:
            raise ValueError("slash in name")

        # Rule 3: indent jump (both first non-blank and subsequent levels)
        if last_level is not None:
            if level < last_level - 1:
                raise ValueError("indent jump")
            # a strictly greater level than the previous violates rule 3
            if level > last_level + 1:
                raise ValueError("indent jump")

        while stack and len(stack) > level:
            stack.pop()

        stack.append(name)
        last_level = level

    return out
