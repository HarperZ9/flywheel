def bucket_counts(values, edges):
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in edges) or len(edges) < 2:
        raise ValueError("edges must be a list of at least 2 non-bool integers in strictly increasing order")
    
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in values):
        raise ValueError("values must be a list of non-bool integers")
    
    if any(v < edges[0] or v > edges[-1] for v in values):
        raise ValueError("all values must be within the range defined by edges")
    
    num_buckets = len(edges) - 1
    counts = [0] * num_buckets
    
    for value in values:
        if value == edges[-1]:
            # Value equal to the last edge goes into the last bucket
            bucket_index = num_buckets - 1
        else:
            bucket_index = next(i for i, edge in enumerate(edges) if value < edge)
        
        counts[bucket_index] += 1
    
    return counts
