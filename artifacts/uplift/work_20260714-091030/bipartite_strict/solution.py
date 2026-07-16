def is_bipartite(adj):
    if not isinstance(adj, list):
        raise ValueError('bad adjacency')
    n = len(adj)
    for i in adj:
        if not isinstance(i, list):
            raise ValueError('bad adjacency')
    for i, jlst in enumerate(adj):
        for j in jlst:
            if not isinstance(j, int) or not 0 <= j < n:
                raise ValueError('bad neighbor')
            if j == i:          # a self-loop is NOT bipartite; symmetry skips it
                return False
    for i in range(n):
        for j in adj[i]:
            if i not in adj[j]:   # every edge must be reciprocated
                raise ValueError('not symmetric')
    color = [None] * n
    def dfs(i, c):
        if color[i] is None:
            color[i] = c
            return all(dfs(j, 1 - c) for j in adj[i])
        return color[i] == c
    # a disconnected graph: start coloring from each uncolored vertex and treat
    # the two halves as independent components (i.e. disjoint unions of bipartite
    # graphs are bipartite); any half that is not bipartite -> False immediately
    for i in range(n):
        if color[i] is None and not dfs(i, 0):
            return False
    return True
