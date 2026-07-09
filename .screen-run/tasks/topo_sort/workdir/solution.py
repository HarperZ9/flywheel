def topo_sort(n, edges):
    adj = [[] for _ in range(n)]
    indeg = [0] * n
    for u, v in edges:
        adj[u].append(v)
        indeg[v] += 1
    stack = [i for i in range(n) if indeg[i] == 0]
    out = []
    while stack:
        u = stack.pop()
        out.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                stack.append(v)
    return out if len(out) == n else None
