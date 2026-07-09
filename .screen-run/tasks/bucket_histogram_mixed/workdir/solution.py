def bucket_counts(values, edges):
    if not isinstance(edges, list) or len(edges) < 2:
        raise ValueError("edges must be a list with at least 2 entries")
    for e in edges:
        if isinstance(e, bool) or not isinstance(e, int):
            raise ValueError("edges must be non-bool ints")
    for i in range(len(edges) - 1):
        if edges[i] >= edges[i + 1]:
            raise ValueError("edges must be strictly increasing")
    if not isinstance(values, list):
        raise ValueError("values must be a list")
    counts = [0] * (len(edges) - 1)
    last = len(edges) - 2
    for v in values:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("values must be non-bool ints")
        if v < edges[0] or v > edges[-1]:
            raise ValueError("value out of range")
        if v == edges[-1]:
            counts[last] += 1
            continue
        lo = 0
        hi = len(edges) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if edges[mid] <= v:
                lo = mid
            else:
                hi = mid
        counts[lo] += 1
    return counts
