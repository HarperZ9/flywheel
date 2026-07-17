def lis_length(nums):
    """
    Calculate the length of the longest strictly increasing subsequence in the given list.

    Args:
        nums: A list of integers representing the sequence.

    Returns:
        The length of the longest strictly increasing subsequence.
    """
    if not nums:
        return 0

    # Initialize a list to store the maximum ending element for each position
    lis = [1] * len(nums)

    for i in range(1, len(nums)):
        for j in range(i):
            if nums[i] > nums[j]:
                lis[i] = max(lis[i], 1 + lis[j])

    return max(lis)
