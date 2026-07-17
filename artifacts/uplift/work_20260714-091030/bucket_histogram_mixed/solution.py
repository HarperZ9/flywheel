def bucket_counts(values, edges):
    if len(edges) < 2 or not all(isinstance(e, int) and not isinstance(e, bool) for e in edges):
        raise ValueError("edges must be a list of at least 2 non-bool ints")
    if any(edges[i] >= edges[i + 1] for i in range(len(edges) - 1)):
        raise ValueError("edges must be strictly increasing integers")
    counts = [0] * (len(edges) - 1)
    lb, ub = min(values), max(values)
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        raise ValueError("values must be a list of non-bool ints")
    lo, hi = edges[0], edges[-1]
    if not (lo <= lb and ub <= hi):
        raise ValueError(f"value outside range [{lo}, {hi}]: {lb}..{ub}")
    last = len(edges) - 2
    for v in values:
        i = 0
        while i < last and edges[i + 1] <= v:
            i += 1
        counts[i] += 1
    return counts
