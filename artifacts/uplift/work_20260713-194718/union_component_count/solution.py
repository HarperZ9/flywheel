def component_count(n: int, edges: list) -> int:
    if not isinstance(n, int) or (isinstance(n, bool)):
        raise ValueError('bad n')
    
    if not isinstance(edges, list):
        raise ValueError('bad edges')

    def validate_edge(edge: tuple):
        if len(edge) != 2:
            return False
        for item in edge:
            if not isinstance(item, int) or (isinstance(item, bool)):
                return False
            if item < 0 or item >= n:
                return False
        return True

    edges_set = set()
    for edge in edges:
        if validate_edge(edge):
            edges_set.add(tuple(sorted(edge)))
        else:
            raise ValueError('bad edge')

    # Remove duplicates by converting set to list
    edges_list = list(edges_set)
    
    count = n  # Initialize with the number of nodes
    visited = [False] * n

    def explore_component(node: int):
        if not visited[node]:
            visited[node] = True
            for edge in edges_list:
                other_node = next((n1, n2) for n1, n2 in edge if node == min(n1, n2))[0]
                if not visited[other_node]:
                    explore_component(other_node)

    for i in range(n):
        if not visited[i]:
            count -= 1
            explore_component(i)
    
    return count
