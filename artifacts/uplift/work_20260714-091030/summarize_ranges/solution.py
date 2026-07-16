def summarize_ranges(nums):
    if not nums:
        return []
    for x in nums:
        if not isinstance(x, int) or isinstance(x, bool):
            raise ValueError("bad item")
    for i in range(1, len(nums)):
        if nums[i] <= nums[i - 1]:
            raise ValueError("not sorted")
    ranges = []
    start = 0
    for i in range(len(nums) - 1):
        if nums[i] + 1 != nums[i + 1]:
            ranges.append(f"{nums[start]}->>{nums[i]}" if i > start else str(nums[start]))
            start = i + 1
    ranges.append(str(nums[-1]) if len(nums) - 1 > start else f"{nums[start]}->>{nums[-1]}")
    return ranges
