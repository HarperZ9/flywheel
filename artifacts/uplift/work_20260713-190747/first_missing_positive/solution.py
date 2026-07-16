def first_missing_positive(nums):
    """
    Returns the smallest positive integer (>= 1) that does not appear in the list.
    
    Args:
    nums : List[int] - A list of integers which may contain duplicates, zeros, and negatives.
    
    Returns:
    int - The smallest positive integer not present in the list.
    
    Note: The input list must NOT be modified.
    
    Example:
    >>> first_missing_positive([3, 4, -1, 1])
    2
    >>> first_missing_positive([1, 2, 0])
    3
    >>> first_missing_positive([-1, -2, -3])
    1
    >>> first_missing_positive([])
    1
    """
    if not nums:
        return 1
    
    n = len(nums)
    for i in range(n):
        while 1 <= nums[i] <= n and nums[nums[i] - 1] != nums[i]:
            nums[nums[i] - 1], nums[i] = nums[i], nums[nums[i] - 1]
    
    for i in range(n):
        if nums[i] != i + 1:
            return i + 1
    return n + 1
