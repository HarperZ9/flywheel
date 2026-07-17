def interval_intersection(a, b):
    i = j = 0
    result = []
    
    while i < len(a) and j < len(b):
        # If both intervals are disjoint, move to the next interval in both lists
        if a[i][1] < b[j][0]:
            i += 1
        elif b[j][1] < a[i][0]:
            j += 1
        else:
            # Calculate intersection start and end (if any)
            start = max(a[i][0], b[j][0])
            end = min(a[i][1], b[j][1])
            
            if start <= end:  # Check for non-empty intersection
                result.append([start, end])
                
            # Non-disjoint intervals, move in both lists to check the next possible intersections
            if a[i][1] < b[j][1]:
                i += 1
            else:
                j += 1
                
    return result
