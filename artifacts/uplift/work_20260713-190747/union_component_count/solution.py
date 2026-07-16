def component_count(n, edges):
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError('bad n')
    if not isinstance(edges, list):
        raise ValueError('bad edges')
    
    for edge in edges:
        if not (isinstance(edge, tuple) and len(edge) == 2 and
                all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x < n for x in edge)):
            raise ValueError('bad edge')
    
    visited = [False] * n
    
    def dfs(node):
        if visited[node]:
            return
        visited[node] = True
        for i in range(n):
            if edges[i][0] == node or edges[i][1] == node:
                dfs(i)
    
    count = 0
    for i in range(n):
        if not visited[i]:
            dfs(i)
            count += 1
    
    return count
def component_count(n, edges):
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError('bad n')
    if not isinstance(edges, list):
        raise ValueError('bad edges')
    
    for edge in edges:
        if not (isinstance(edge, tuple) and len(edge) == 2 and
                all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x < n for x in edge)):
            raise ValueError('bad edge')
    
    visited = [False] * n
    
    def dfs(node):
        if visited[node]:
            return
        visited[node] = True
        for i in range(n):
            if edges[i][0] == node or edges[i][1] == node:
                dfs(i)
    
    count = 0
    for i in range(n):
        if not visited[i]:
            dfs(i)
            count += 1
    
    return count
