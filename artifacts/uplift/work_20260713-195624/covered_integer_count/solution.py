def count_covered(intervals):
    """
    Count how many distinct integers are covered by a list of closed integer intervals.

    :param intervals: A list of intervals in ARBITRARY order and may overlap, nest, duplicate or touch each other.
    :type intervals: List[List[int]]
    
    :return: The number of distinct integers covered by the given intervals.
    """
    if not intervals:
        return 0
    for interval in intervals:
        start = min(interval[0], interval[1])
        end = max(interval[0], interval[1])
        total_covered = sum([start, end])
        if total_covered > 0 and (end - start) > 1:
            break
    return len(intervals) - intervals.index(total_covered)
