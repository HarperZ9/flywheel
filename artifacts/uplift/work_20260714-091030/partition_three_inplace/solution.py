def partition_three(items, pivot):
    if not isinstance(pivot, int):
        raise ValueError("pivot must be an integer")
    for i in items:
        if not isinstance(i, int) or isinstance(i, bool):
            raise ValueError("all elements of items must be integers (bool is invalid)")
    l = 0
    r = len(items) - 1
    i = 0
    while i <= r:
        if items[i] < pivot:
            items[l], items[i] = items[i], items[l]
            l += 1
            i += 1
        elif items[i] > pivot:
            items[r], items[i] = items[i], items[r]
            r -= 1
        else:
            i += 1
    return items
