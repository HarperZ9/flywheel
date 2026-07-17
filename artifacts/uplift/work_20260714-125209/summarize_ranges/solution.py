def summarize_ranges(nums):
    if not nums:
        return []
    for x in nums:
        if not isinstance(x, int) or isinstance(x, bool):
            raise ValueError('bad item')
    for i in range(1, len(nums)):
        if nums[i] <= nums[i - 1]:
            raise ValueError('not sorted')
    out = []
    start = end = nums[0]
    for i in range(1, len(nums)):
        if nums[i] == nums[i - 1] + 1:
            end = nums[i]
        else:
            out.append(str(start) if start == end else f'{start}->{end}')
            start = end = nums[i]
    out.append(str(start) if start == end else f'{start}->{end}')
    return out
