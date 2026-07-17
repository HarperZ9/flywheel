def first_missing_positive(nums: List[int]) -> int:
    n = len(nums)
    # Place each number in its right place, i.e., nums[i] == i + 1
    for i in range(n):
        while 1 <= nums[i] <= n and nums[nums[i] - 1] != nums[i]:
            # Swap nums[i] with nums[nums[i] - 1]
            idx = nums[i] - 1
            nums[i], nums[idx] = nums[idx], nums[i]
    # The first index where the number is not i + 1 is the missing one
    for i in range(n):
        if nums[i] != i + 1:
            return i + 1
    return n + 1
