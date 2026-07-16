def rotate(items, k):
    if not isinstance(items, list):
        raise ValueError('bad input')
    
    n = len(items)
    if not isinstance(k, int) or isinstance(k, bool):
        raise ValueError('bad shift')
    
    if n == 0:
        return []
    
    k = k % n  # Handle cases where k >= n
    rotated_items = items[-k:] + items[:-k]
    return rotated_items
