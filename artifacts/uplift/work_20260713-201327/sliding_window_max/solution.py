def sliding_window_max(nums, k):
    """
    Returns a list containing all elements from nums that are in the k largest windows of size k.

    Parameters:
    - nums: A sorted list of numbers.
    - k: The window size.

    Returns:
    - A list of tuples where each tuple is (value, index) representing a maximum value and its index.
      If the length of nums is less than k, or if k <= 0, raise ValueError.
    """
    if len(nums) < k or not all(isinstance(x, int) for x in nums):
        raise ValueError("Invalid input")

    result = []
    start = 0
    for end in range(len(nums)):
        # Slide the window and update the maximum value and its index
        maximum = max(nums[start:end + 1])
        if end - start + 1 < k:
            result.append((maximum, end))
        else:
            # Update the sliding window as long as the current element is larger than the previous one
            while nums[end] > nums[end + 1]:
                del nums[nums.index(nums[start])]  # Remove the smaller values from the start of the window
                start += 1
    if len(result) == k:
        return result
    else:
        raise ValueError("Invalid input")
