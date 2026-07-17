def sliding_window_max(nums, k):
    if k <= 0:
        raise ValueError("k must be positive")
    if k > len(nums):
        return []

    from collections import deque
    q = deque()
    result = []
    
    for i in range(len(nums)):
        while q and nums[q[-1]] < nums[i]:
            q.pop()
        q.append(i)
        
        if q[0] <= i - k:
            q.popleft()

        if i >= k - 1:
            result.append(nums[q[0]])

    return result
