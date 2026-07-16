def has_cycle(nxt):
    if not nxt or len(nxt) == 1:
        return False

    visited = set()
    stack = [(0, -2)]

    while stack:
        (node, last) = stack.pop()
        
        if node in visited and last != -1: 
            # This checks for a cycle where the link points to itself
            return True
        
        if nxt[node] == -1:  
            continue

        if nxt[node] not in visited:
            visited.add(node)
            stack.append((node, nxt[node]))
            stack.append((nxt[node], node))

    return False
