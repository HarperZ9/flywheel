def bucket_counts(values, edges):
    if not all(isinstance(i, int) and isinstance(j, int) for i, j in zip(edges, edges[1:])):
        raise ValueError("Edges must be a list of at least 2 non-bool ints.")
    
    if len(set(edges).difference({i for i in range(min(edges), max(edges)+1)})) > 0:
        raise ValueError("Edges must be strictly increasing and cover the entire space of values.")
    
    if any(v not in (int, float) or v < edges[0] or v > edges[-1] for v in values):
        raise ValueError("Values list contains out-of-bounds integers or non-integers.")
    
    if len(edges) < 2:
        return [0]
    
    counts = [0] * (len(edges) - 1)
    for value in sorted(values):  # Ensure deterministic output
        for i, edge in enumerate(edges[:-1]):
            if edges[i] <= value < edges[i+1]:
                counts[i] += 1
                break
        else:
            counts[-2] += 1
    
    return counts
