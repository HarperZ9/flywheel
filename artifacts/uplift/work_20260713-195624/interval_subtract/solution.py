from typing import List

def interval_subtract(a: List[List[int]], b: List[List[int]]) -> List[List[int]]:
    """
    Computes the difference of two closed INTEGER interval lists:
    Each list contains [start, end] pairs of ints; both lists are already sorted by start.
    
    Args:
    a (List[List[int]]): First interval list
    b (List[List[int]]): Second interval list
    
    Returns:
    List[List[int]]: The difference between the two intervals after subtracting.
                      - For each interval, either [start, end] or []
                      - If an interval starts with 'b' in a and not in b, it remains unchanged
                      - If an interval has no matching part in b, it is removed from the result as per the provided semantics
    """
    # Remove empty intervals from both lists
    if not any(interval for interval in a):
        return [interval for interval in b]
    elif not any(interval for interval in b):
        return [interval for interval in a]

    # Compute the difference by first keeping elements equal to find common parts, then removing those that are not
    result = []
    i = 0
    j = 0
    
    while i < len(a) and j < len(b):
        if a[i][0] <= b[j][1]:
            result.append([max(a[i][0], b[j][0]), min(a[i][1], b[j][1])])
            # Remove overlapping intervals from either side
            if max(a[i][0], b[j][0]) > min(a[i][1], b[j][1]):
                i += 1
            else:
                j += 1
    
    return result + [interval for interval in b if not any(interval in a) and (a[i-1] is None or interval[0] <= a[i-1][1])]
