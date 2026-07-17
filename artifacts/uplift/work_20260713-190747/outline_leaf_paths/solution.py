def outline_paths(lines):
    if not lines:
        return []

    indent_stack = []
    path_stack = [[]]
    
    for line in lines:
        # Skip blank lines
        if not line.strip():
            continue
        
        # Determine the level of the current line
        spaces = len(line) - len(line.lstrip(' '))
        if '\t' in line[:spaces]:
            raise ValueError("tab in indent")
        
        depth = spaces // 2
        while indent_stack and indent_stack[-1] != (depth - 1):
            path_stack.pop()
            indent_stack.pop()
        
        if '/' in line.strip():
            raise ValueError("slash in name")
        
        # Add the current node to the path
        path_stack[-1].append(line.strip())
        # Push a new indent level onto the stack
        indent_stack.append(depth)
    
    # Collect leaf paths
    leaf_paths = ["/".join(path) for path in path_stack if not indent_stack or indent_stack[-1] == 0]
    
    return leaf_paths
def outline_paths(lines):
    if not lines:
        return []

    indent_stack = []
    path_stack = [[]]

    for line in lines:
        # Skip blank lines
        if not line.strip():
            continue

        # Determine the level of the current line
        spaces = len(line) - len(line.lstrip(' '))
        if '\t' in line[:spaces]:
            raise ValueError("tab in indent")
        
        depth = spaces // 2
        while indent_stack and indent_stack[-1] != (depth - 1):
            path_stack.pop()
            indent_stack.pop()
        
        if '/' in line.strip():
            raise ValueError("slash in name")
        
        # Add the current node to the path
        path_stack[-1].append(line.strip())
        # Push a new indent level onto the stack
        indent_stack.append(depth)
    
    # Collect leaf paths
    leaf_paths = ["/".join(path) for path in path_stack if not indent_stack or indent_stack[-1] == 0]
    
    return leaf_paths
