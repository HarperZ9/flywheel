def has_cycle(nxt):
    if not nxt:
        return False

    def visit(node, visited):
        if node == -1:
            return False
        if node in visited:
            return True
        visited.add(node)
        next_node = nxt[node]
        return visit(next_node, visited)

    visited = set()
    return visit(0, visited)
