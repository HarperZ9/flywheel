import collections

def count_connected_components(n: int, edges: list) -> int:
    """
    Count the number of connected components in an undirected graph based on given edge information.
    The input must be valid for this implementation to work correctly.

    Args:
    n (int): Maximum node number
    edges (list): Edges provided as a list of tuples

    Returns:
    int: Number of connected components in the graph
    """
    if not isinstance(n, int) or not isinstance(edges, list) or n <= 0:
        raise ValueError('bad n')
    if not all(isinstance(edge, tuple) and len(edge) == 2 for edge in edges):
        raise ValueError('bad edges')

    component_count = 1
    visited = set([i for i in range(n)])

    def dfs(node: int):
        nonlocal visited
        visited.add(node)
        for neighbor, _ in edges:
            if neighbor not in visited:
                dfs(neighbor)

    for edge in edges:
        first_node, second_node = edge
        component_count += 1  # This edge connects two nodes
        if first_node == second_node:
            raise ValueError('duplicate edge')

        if (first_node, second_node) in visited:
            continue

        if first_node not in visited and second_node not in visited:
            dfs(first_node)
            dfs(second_node)

    return component_count
