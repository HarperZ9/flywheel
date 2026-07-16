def bucket_counts(values, edges):
    if not isinstance(edges, list) or any(not isinstance(edge, int) for edge in edges):
        raise ValueError("Edges must be a list of integers")
    
    if len(edges) < 2:
        raise ValueError("Edges list must contain at least 2 elements")

    if any(isinstance(edge, bool) for edge in edges):
        raise ValueError("All elements in edges must be integers")

    if not isinstance(values, list):
        raise ValueError("Values must be a list of integers")

    if any(not isinstance(val, int) for val in values):
        raise ValueError("All elements in values must be integers")
    
    if min(edges) < float('-inf') or max(edges) > float('inf'):
        raise ValueError("Edges must represent valid integer boundaries")
    
    if not all(isinstance(edge, (int)) and edge >= 0 for edge in edges[1:]):
        raise ValueError("Edges must be strictly increasing non-negative integers")

    counts = [0] * (len(edges) - 1)
    if not values:
        return counts

    min_val = min(values)
    max_val = max(values)

    if min_val < edges[0] or max_val > edges[-1]:
        raise ValueError("Values must be within the defined edge range")

    for value in values:
        for i, (start, end) in enumerate(zip(edges[:-1], edges[1:])):
            if start <= value < end:
                counts[i] += 1
                break

    return counts
