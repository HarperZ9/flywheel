def summarize_ranges(nums):
    if not all(isinstance(x, int) for x in nums):
        raise ValueError('bad item')
    
    if len(nums) != sorted(set(nums)):
        raise ValueError('not sorted')
    
    summarized = []
    i = 0
    while i < len(nums):
        start = nums[i]
        j = i + 1
        while j < len(nums) and nums[j] == nums[i]:
            j += 1
        
        if j > i + 1:
            summary = f"{start}-{nums[j-1]}>"
        else:
            summary = str(start)
        
        summarized.append(summary)
        i = j
    
    return summarized
