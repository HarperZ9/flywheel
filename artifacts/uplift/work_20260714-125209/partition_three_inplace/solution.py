def partition_three(items, pivot):
    if not isinstance(pivot, int):
        raise ValueError("pivot must be an integer")
    if not all(isinstance(x, int) for x in items):
        raise ValueError("all elements of items must be integers")
    equal = [x for x in items if x == pivot]
    less  = [x for x in items if x <  pivot]
    more  = [x for x in items if x >  pivot]
    items[:] = less + equal + more
    return items
