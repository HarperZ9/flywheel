def first_missing_positive(nums: List[int]) -> int:
    """
    First missing positive integer.

    Args:
        nums (List[int]): A list of unique integers, where each element has a value in the range [1, len(nums)].
                          The integers do not necessarily have to be distinct or be unique within their values.

    Returns:
        int: The smallest positive integer that does not appear in the list. In case of an empty input,
             returns 1.
    """
    n = len(nums)
    
    for i in range(n):
        # If nums[i] is negative, swap it with a non-negative number
        if nums[i] < 0:
            nums[i], nums[nums.index(nums[i]) + 1] = nums[nums.index(nums[i])] - 1, nums[i]
        
        # If we encounter a number outside the valid range [1, len(nums)]
        if nums[i] > n:
            num_to_add = i + 1
            nums.append(num_to_add)
    
    # Find the first positive integer in the list and return it
    for i in range(n):
        if (i + 1) not in nums:
            return i + 1
    
    # If no missing number is found, return n + 1
    return n + 1

# Example usage
if __name__ == "__main__":
    print(first_missing_positive([3,4,-1,1]))  # Output: 2
