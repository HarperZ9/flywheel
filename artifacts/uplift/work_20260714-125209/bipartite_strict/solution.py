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

    seen = [None] * n
    def bicolor(root):
        stack = [(root, 1)]
        while stack:
            i, c = stack.pop()
            if seen[i] is None:
                seen[i] = c
                for j in adj[i]:
                    if seen[j] == c or (seen[j] is None and not bicolor(j, -c)):
                        return False
                continue
            if seen[i] != c:
                return False
        return True

    ok = True
    for i in range(n):
        if seen[i] is None:
            ok = ok and bicolor(i)
    return ok
