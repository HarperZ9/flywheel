def interval_subtract(a, b):
    if not all(start <= end for start, end in a + b):
        raise ValueError('bad interval')

    result = []
    i, j = 0, 0

    while i < len(a) and j < len(b):
        # Handle overlapping intervals
        if a[i][1] < b[j][1]:
            end = min(a[i][1], b[j][1])
            if a[i][0] <= b[j][0] - 1:
                result.append([a[i][0], b[j][0] - 1])
            i += 1
        else:
            end = min(a[i][1], b[j][1])
            if b[j][0] <= a[i][0] - 1:
                result.append([b[j][0], a[i][0] - 1])
            j += 1

    # Add remaining intervals from a
    while i < len(a):
        result.append([a[i][0], a[i][1]])
        i += 1

    # Add remaining intervals from b (they are already in correct order)
    
    return result
