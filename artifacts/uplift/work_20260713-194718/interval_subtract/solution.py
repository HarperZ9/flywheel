def interval_subtract(a, b):
    if not a or not b:
        return a  # Return input list a if b is empty, or return input a itself if a is empty.
    
    i, j = 0, 0
    result = []
    
    while i < len(a) and j < len(b):
        la, ra = a[i][0], a[i][1]
        lb, rb = b[j][0], b[j][1]
        
        # Check if interval in 'b' bites into an interval of 'a'
        if lb <= ra:
            # If it bites all the way
            if lb >= la and rb <= ra:
                j += 1
            # Otherwise, add a[i] to result as it could not be subtracted completely.
            else:
                result.append([la, ra])
        else:
            i += 1
    
    # Add remaining intervals from 'a' that weren't touched by 'b'
    while i < len(a):
        la, ra = a[i][0], a[i][1]
        result.append([la, ra])
        i += 1

    return result
