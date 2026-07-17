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
    last_bucket_index = len(counts)

    for v in values:
        if not isinstance(v, int):
            raise ValueError("values must be a list of non-bool ints")
        if v < min_edge or v > max_edge:
            raise ValueError(f"value {v} out of bounds [{min_edge}, {max_edge}]")

        start = 0
        end = last_bucket_index

        while start < end:
            mid = (start + end) // 2
            low = edges[mid]
            high = edges[mid + 1]

            if v == high and mid != last_bucket_index - 1:
                # interior edge: belongs to right bucket
                counts[mid + 1] += 1
            elif low <= v < high or (mid == last_bucket_index - 1 and low <= v <= max_edge):
                counts[mid] += 1
                break

    return counts
