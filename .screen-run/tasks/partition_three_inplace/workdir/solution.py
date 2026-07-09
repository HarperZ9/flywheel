def partition_three(items, pivot):
    def check_int(x):
        if isinstance(x, bool) or not isinstance(x, int):
            raise ValueError("expected int, not bool/other")

    check_int(pivot)
    for x in items:
        check_int(x)
    less = [x for x in items if x < pivot]
    equal = [x for x in items if x == pivot]
    greater = [x for x in items if x > pivot]
    items[:] = less + equal + greater
    return items
