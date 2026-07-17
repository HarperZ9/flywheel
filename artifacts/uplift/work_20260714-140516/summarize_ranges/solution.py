def summarize_ranges(nums):
    if not nums:
        return []
    for n in nums:
        if not isinstance(n, int) or isinstance(n, bool):
            raise ValueError('bad item')
    for i in range(1, len(nums)):
        if nums[i] <= nums[i - 1]:
            raise ValueError('not sorted')
    runs = []
    start = end = None
    for n in nums:
        if end is not None and end + 1 == n:
            end += 1
        else:
            if start is not None:
                runs.append(f'{start}-{end}' if end > start else str(start))
            start = end = n
    if start is not None:
        runs.append(f'{start}-{end}' if end > start else str(start))
    return runs
