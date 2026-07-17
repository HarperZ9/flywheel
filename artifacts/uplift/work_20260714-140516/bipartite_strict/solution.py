def is_bipartite(adj):
    if not isinstance(adj, list):
        raise ValueError("bad adjacency")
    n = len(adj)
    for i in range(n):
        if not isinstance(adj[i], list):
            raise ValueError("bad adjacency")
        for j in adj[i]:
            if not isinstance(j, int) or not (0 <= j < n):
                raise ValueError("bad neighbor")
    for i in range(n):
        for j in adj[i]:
            if i not in adj[j]:
                raise ValueError("not symmetric")

    seen = [False] * n
    bipartite = [None] * n

    def bfs(s):
        level = 0
        q, bq = [], []
        q.append(s)
        res = True
        while q:
            x = q.pop()
            if not res:
                continue
            seen[x] = True
            if bipartite[x] is None:
                bp = level % 2
            else:
                bp = bipartite[x]
            for y in adj[x]:
                if y == x:           # self-loop -> NOT bipartite
                    res = False; break
                if not seen[y]:
                    seen[y] = True; bq.append(y)
                if bipartite[y] is None:
                    bipartite[y] = 1 - bp
                else:
                    res &= (bipartite[y] == 1 - bp)
            if not q:
                level += 1
                q, bq = bq, q
        return res

    for i in range(n):
        if not seen[i]:
            if not bfs(i):           # one disconnected component alone -> NOT bipartite
                return False
    return True
