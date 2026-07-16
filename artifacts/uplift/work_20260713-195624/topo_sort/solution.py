def topo_sort(n, edges):
    """
    Given an undirected graph with labeled nodes 0 to n-1 and directed edges [u, v] where
    u comes before v due to the requirement that there must be no cycle, return any valid topological
    order as a list. If the graph has a cycle, return None.

    Example:
    >>> topo_sort(5, [[0, 1], [3, 4], [1, 2]])
    [0, 1, 3, 2, 4]
    """
    from collections import defaultdict

    # Initialize graph
    graph = defaultdict(list)
    for u, v in edges:
        graph[u].append(v)

    visited = [False] * n
    top_order = []

    def dfs(node):
        if not visited[node]:
            visited[node] = True
            for neighbor in graph[node]:
                dfs(neighbor)
            top_order.append(node)

    # Perform DFS on each unvisited node
    for i in range(n):
        if not visited[i]:
            dfs(i)

    return top_order if len(top_order) == n else None
