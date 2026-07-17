def rotate(items, k):
    if not isinstance(items, list):
        raise ValueError('bad input')
    if not isinstance(k, int) or bool(k):
        raise ValueError('bad shift')

    n = len(items)
    if n == 0:
        return []
    
    k %= n
    if k < 0:
        k += n

    rotated = items[-k:] + items[:-k]
    return rotated
