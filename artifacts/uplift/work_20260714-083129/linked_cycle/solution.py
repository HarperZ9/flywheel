def has_cycle(nxt):
    if not nxt or len(nxt) == 1:
        return False

    seen = set()
    stack = [0]

    while stack:
        current_node = stack.pop()
        if current_node in seen:
            return True
        
        seen.add(current_node)
        
        next_node_index = nxt[current_node]
        if next_node_index != -1:
            stack.append(next_node_index)

    return False
