def is_bipartite(adj):
    if not isinstance(adj, list):
        raise ValueError('bad adjacency')
    
    n = len(adj)
    for i in range(n):
        if not isinstance(adj[i], list):
            raise ValueError('bad neighbor')
        adj[i] = set(adj[i])  # Convert to set to handle duplicates and speed up operations
    
    for i in range(n):
        for j in adj[i]:
            if j >= n or i not in adj[j]:
                raise ValueError('not symmetric')
    
    from collections import defaultdict

    def bfs(start):
        queue = [start]
        color[start] = 0
        while queue:
            node = queue.pop(0)
            for neighbor in adj[node]:
                if neighbor_color[neighbor] == color[node]:
                    return False
                if neighbor_color[neighbor] == -1:
                    neighbor_color[neighbor] = 1 - color[node]
                    queue.append(neighbor)
        return True

    color = [-1] * n  # -1 means uncolored, 0 and 1 are colors
    for i in range(n):
        if color[i] == -1:
            neighbor_color = defaultdict(lambda: -1)
            if not bfs(i):
                return False
    
    return True
