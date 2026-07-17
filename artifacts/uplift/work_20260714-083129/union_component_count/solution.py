def component_count(n: int, edges: list) -> int:
    if not isinstance(n, int) or (isinstance(n, bool)):
        raise ValueError('bad n')
    
    if not isinstance(edges, list):
        raise ValueError('bad edges')

    for edge in edges:
        if not (isinstance(edge, tuple) and len(edge) == 2):
            raise ValueError('bad edge')
        
        x, y = edge
        if not (isinstance(x, int) and isinstance(y, int)):
            raise ValueError('bad edge')
        if any(not (-1 <= val < n) for val in [x, y]):
            raise ValueError('bad edge')

    components = 0
    visited = set()

    def dfs(node: int):
        if node not in visited:
            visited.add(node)
            for nei in edges:
                x, y = nei
                if x == node or y == node and (x, y) not in visited:
                    dfs(y)
                    dfs(x)

    for i in range(n):
        if i not in visited:
            components += 1
            dfs(i)

    return components
