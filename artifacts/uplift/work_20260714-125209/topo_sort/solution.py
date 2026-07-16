def topo_sort(n, edges):
    adj = [[] for _ in range(n)]
    outdegree = [0] * n
    for u, v in edges:
        if not (0 <= u < n and 0 <= v < n): return None
        adj[u].append(v); outdegree[v] += 1
    order = []
    q = deque(u for u in range(n) if outdegree[u] == 0)
    while q:
        u = q.popleft(); order.append(u)
        for v in adj[u]:
            outdegree[v] -= 1; (q.append(v) if outdegree[v]==0 else None)
    return order if len(order)==n else None
