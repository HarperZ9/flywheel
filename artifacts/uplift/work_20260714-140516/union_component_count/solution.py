def component_count(n, edges):
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError('bad n')
    if not isinstance(edges, list):
        raise ValueError('bad edges')
    for e in edges:
        if not isinstance(e, tuple) or len(e) != 2:
            raise ValueError('bad edge')
        a, b = e
        if not (isinstance(a, int) and isinstance(b, int)):
            raise ValueError('bad edge')
        if isinstance(a, bool) or isinstance(b, bool):
            raise ValueError('bad edge')
        if not (0 <= a < n and 0 <= b < n):
            raise ValueError('bad edge')

    parent = list(range(n))

    def find(x):
        while x != parent[x]:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        pa = find(a)
        pb = find(b)
        if pa != pb:
            parent[pb] = pa

    seen = set()
    for i in range(n):
        seen.add(find(i))
    return len(seen)
