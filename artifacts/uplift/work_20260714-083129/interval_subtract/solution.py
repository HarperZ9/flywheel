def interval_subtract(a, b):
    if not a and b:
        return []
    if a and not b:
        return list(a)
    
    result = []
    i, j = 0, 0
    
    while i < len(a) or j < len(b):
        if i == len(a) or (j < len(b) and a[i][0] > b[j][1]):
            result.append(a[i])
            i += 1
        elif j == len(b) or (i < len(a) and a[i][0] <= b[j][1]):
            j += 1
        else:
            # Found a common interval that needs to be checked for overlap with any remaining intervals in 'a'
            new_start, new_end = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
            if result and result[-1][1] >= new_start - 1:
                # There is an overlap to handle
                last_interval = result.pop()
                result.append([last_interval[0], new_end])
            elif not result or result[-1][1] < new_start - 1:
                # No overlap, add the non-overlapping part and continue.
                if i < len(a) and a[i][0] > new_end:
                    result.append([new_start, new_end])
        
    return result
