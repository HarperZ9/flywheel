def merge_sorted(lists):
    if not lists:
        return []
    from heapq import merge
    return list(merge(*lists))
