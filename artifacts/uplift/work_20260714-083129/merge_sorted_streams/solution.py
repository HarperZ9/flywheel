def merge_sorted(lists):
    if not lists or len(lists) == 0:
        return []
    
    # Create an empty heap and add all elements from the input list to it.
    import heapq
    min_heap = []
    for index, lst in enumerate(lists):
        if lst:
            heapq.heappush(min_heap, (lst[0], index, 0))
    
    result = []
    while min_heap:
        value, list_index, element_index = heapq.heappop(min_heap)
        
        # Append the current element to the result
        result.append(value)
        
        # If there are more elements in the list, push the next one onto the heap.
        if element_index + 1 < len(lists[list_index]):
            next_value = lists[list_index][element_index + 1]
            heapq.heappush(min_heap, (next_value, list_index, element_index + 1))
    
    return result
