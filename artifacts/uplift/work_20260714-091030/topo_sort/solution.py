def topo_sort(n: int, edges: list[list[int]]) -> list[int]:
    adj = [[] for _ in range(n)]
    outdeg = [0] * n
    for u, v in edges:
        if u >= n or v >= n: return None  # edge may not reference a missing node
        adj[u].append(v); outdeg[v] += 1

    q = deque(u for u in range(n) if outdeg[u] == 0)
    order = []
    while q:
        u = q.popleft(); order.append(u)
        for v in adj[u]:
            outdeg[v] -= 1
            if outdeg[v] == 0: q.append(v)
    return order if len(order) == n else None
