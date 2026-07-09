def sliding_window_max(nums, k):
    if k <= 0:
        raise ValueError(k)
    if k > len(nums):
        return []
    from collections import deque
    dq, out = deque(), []
    for i, x in enumerate(nums):
        while dq and nums[dq[-1]] <= x:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - k:
            dq.popleft()
        if i >= k - 1:
            out.append(nums[dq[0]])
    return out
