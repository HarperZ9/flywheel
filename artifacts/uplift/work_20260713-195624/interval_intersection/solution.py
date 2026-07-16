def interval_intersection(a: List[List[int]], b: List[List[int]]) -> List[List[int]]:
    """
    Given two lists of closed integer intervals, return the intersection of their intervals.
    
    Each list is sorted and internally disjoint. Each element in the interval [start, end]
    represents its start and end time respectively.
    
    Example:
        >>> interval_intersection([[1, 3], [5, 6]])
        [[2, 6]]
        
        # Interval (1, 3) and (5, 6) intersect each other because they both have a 4th element (end).
    """
    # Sort the intervals by their start time
    a = sorted(a)
    b = sorted(b)
    
    # Find the intersection of the two lists
    result = [min(a[i][0], b[i][0]) for i in range(len(a)) if min(a[i][0], b[i][0]) <= max(a[i+1][1], b[i+1][1])]
    
    return result
