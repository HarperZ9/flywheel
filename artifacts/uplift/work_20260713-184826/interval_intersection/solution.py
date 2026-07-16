def interval_intersection(a, b):
    i, j = 0, 0
    result = []
    
    while i < len(a) and j < len(b):
        # Check if there is an intersection
        start = max(a[i][0], b[j][0])
        end = min(a[i][1], b[j][1])
        
        if start <= end:
            result.append([start, end])
            
        # Move to the next interval in the list that ended first
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
            
    return result
