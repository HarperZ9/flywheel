def bucket_counts(values, edges):
    if len(edges) < 2 or any(not isinstance(e, int) for e in edges):
        raise ValueError("edges must be a list of at least 2 non-bool ints")
    if not all(isinstance(v, int) for v in values):
        raise ValueError("values must be a list of non-bool ints")
    if len(edges) != len(set(edges)):
        raise ValueError("edges must have no duplicate entries")
    if any(a >= b for a, b in zip(edges, edges[1:])):
        raise ValueError("edges must be strictly increasing")

    min_edge = edges[0]
    max_edge = edges[-1]
    counts = [0] * (len(edges) - 1)
    last_bucket_index = len(counts) - 1

    for v in values:
        if v < min_edge or v > max_edge:
            raise ValueError(f"value {v} exceeds edge range [{min_edge}, {max_edge}]")
        # Find the bucket index by binary search into edges
        lo, hi = 0, len(edges) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if v >= edges[mid]:
                lo = mid + 1
            else:
                hi = mid
        # lo is the first bucket index for which values[lo] <= v
        if v == max_edge and lo > last_bucket_index:
            lo -= 1
        counts[lo] += 1

    return counts
