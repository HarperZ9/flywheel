def merge_sorted(lists):
    import heapq
    h = [(lst[0], i, 0) for i, lst in enumerate(lists) if lst]
    heapq.heapify(h)
    out = []
    while h:
        val, i, j = heapq.heappop(h)
        out.append(val)
        if j + 1 < len(lists[i]):
            heapq.heappush(h, (lists[i][j + 1], i, j + 1))
    return out
