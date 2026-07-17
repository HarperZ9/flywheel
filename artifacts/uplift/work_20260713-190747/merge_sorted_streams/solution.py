def merge_sorted(lists):
    from heapq import heapify, heappop
    
    # Convert each list into an iterator and push the first element to the heap.
    heap = [(lst[i], i) for i in range(len(lst)) if i < len(lst) and lst[i] is not None]
    heapify(heap)
    
    result = []
    
    while heap:
        val, idx = heappop(heap)
        result.append(val)
        
        # Push the next element from the same list to the heap, if available.
        if (idx + 1) < len(lists[idx]):
            next_tuple = (lists[idx][idx + 1], idx + 1)
            heappush(heap, next_tuple)
    
    return result
