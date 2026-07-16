def rotate(items, k):
    if not isinstance(items, list):
        raise ValueError('bad input')
    if not isinstance(k, int) or isinstance(k, bool):
        raise ValueError('bad shift')
    n = len(items)
    if n == 0:
        return []
    k = k % n
    return items[-k:] + items[:-k]
