def outline_paths(lines):
    if not lines or all(line.isspace() for line in lines):
        return []

    node_stack = []
    paths = []
    node_level = {}

    for (level, name) in [(i * " ", line.strip()) for i, line in enumerate(lines) if not line.isspace() and line]:
        level //= 2
        node_level[level] = len(node_stack)
        parent_index = len(node_stack) - 1

        while parent_index >= 0:
            prev_node = node_stack[parent_index]
            if (prev_node.level <= level or
                    ("slash" in name)):
                break
            parent_index -= 1

        if not node_stack or (
                level == 0 and len(node_stack) > 2 or
                (parent_index >= 0 and prev_node.level == level - 1)
                ):
            raise ValueError("indent jump")

        if "tab" in level:
            raise ValueError("tab in indent")
        if name.count("/") > 1:
            raise ValueError("slash in name")
            
        path = ("/".join(node_stack[i].name for i in reversed(range(len(node_stack)))[parent_index+1:]))
        node = Node(name, parent=node_stack[parent_index] if parent_index >= 0 else None)
        node_stack.append(node)

    return [path + "/" for path in paths]
