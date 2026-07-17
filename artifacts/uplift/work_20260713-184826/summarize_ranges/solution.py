def summarize_ranges(nums):
    if not nums:
        return []
    
    if any(not isinstance(x, int) for x in nums):
        raise ValueError('bad item')
    
    if len(nums) == 1:
        return [str(nums[0])]
    
    def format_range(start, end):
        return str(start) + (f'> {end}' if start != end else '')
    
    result = []
    i = 0
    while i < len(nums):
        start = nums[i]
        j = i + 1
        while j < len(nums) and nums[j] == nums[j - 1] + 1:
            j += 1
        end = nums[j - 1]
        result.append(format_range(start, end))
        i = j
    
    return result
