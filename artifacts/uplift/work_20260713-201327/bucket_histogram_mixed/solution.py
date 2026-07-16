import bisect

def bucket_counts(values, edges):
    """
    Histograms an integer value into buckets defined by a set of edge intervals,
    with mixed boundary semantics.

    Parameters:
    values (list of int): The input values.
    edges (list of tuple (int, int)): The edge intervals for which to create the histogram.

    Returns:
    list: A list of counts representing each bucket's count. If n < len(edges), then all
          resulting lists are empty and return an empty list; otherwise they do contain elements.
    """
    if not edges or min(edges) >= max(values):
        raise ValueError("Invalid edge intervals")

    n = len(edges)
    buckets = [edges[i] for i in range(n-1)]
    bucket_counts = []

    boundary = 0
    current_bucket = -1

    for index, (start, end) in enumerate(edges):
        if start > edges[-1]:
            raise ValueError("Values must be strictly increasing")
        
        while current_bucket < n and values[index] >= buckets[current_bucket + 1][1]:
            current_bucket += 1
        boundary = max(boundary, current_bucket)
        bucket_counts.append(boundaries[boundary])
        boundaries[boundary] = index

    return bucket_counts
