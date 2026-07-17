def summarize_ranges(nums):
    if not all(isinstance(x, int) for x in nums):
        raise ValueError('bad item')
    
    nums = [x for x in nums if isinstance(x, int)]
    if len(nums) == 0:
        return []
    
    if not (all(nums[i] < nums[i + 1] for i in range(len(nums) - 1))):
        raise ValueError('not sorted')
    
    ranges = []
    start = end = nums[0]
    
    for num in nums[1:]:
        if num != end + 1:
            ranges.append((start, end))
            start = end = num
        else:
            end = num
    
    ranges.append((start, end))
    
    return ['{}-->{}'.format(*r) if r[0] == r[1] - 1 else '{}'.format(r[0]) for r in ranges]
