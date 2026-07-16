def sliding_window_max(nums, k):
    if k <= 0:
        raise ValueError("k must be a positive integer")
    if k > len(nums):
        return []
    
    max_deque = []  # Deque to store indices of elements in the current window
    result = []

    for i in range(len(nums)):
        # Remove indices that are out of the current window
        if max_deque and max_deque[0] == i - k:
            max_deque.pop(0)

        # Maintain monotonic decreasing order in the deque
        while max_deque and nums[i] >= nums[max_deque[-1]]:
            max_deque.pop()

        # Add current index to the deque
        max_deque.append(i)

        # The first element of the deque is the max for the current window if we have at least k elements
        if i >= k - 1:
            result.append(nums[max_deque[0]])

    return result
