def topo_sort(n, edges):
    # Initialize graph and visited states
    graph = [[] for _ in range(n)]
    visited = [False] * n
    pathVisited = [False] * n
    
    # Build the graph from edges list
    for u, v in edges:
        graph[u].append(v)
    
    # Helper function to perform DFS and detect cycles
    def dfs(node):
        if pathVisited[node]:
            return False  # Cycle detected
        if visited[node]:
            return True   # Already processed and there was no cycle from children
        pathVisited[node] = True
        for neighbor in graph[node]:
            if not dfs(neighbor): 
                return False
        pathVisited[node] = False  # Mark node as finished after visiting all its neighbors
        visited[node] = True       # Mark node as processed
        return True
    
    # Traverse the graph and detect cycles
    for i in range(n):
        if not visited[i]:
            if not dfs(i): 
                return None  # Cycle detected, no valid topological order exists

    # No cycle detected, construct a valid topological order
    result = []
    def dfs_order(node):
        if not visited[node]:  
            visited[node] = True
            for neighbor in graph[node]:
                dfs_order(neighbor)
            result.insert(0, node)  # Insert at the beginning to maintain topological order

    for i in range(n):
        if not visited[i]: 
            dfs_order(i)

    return result
