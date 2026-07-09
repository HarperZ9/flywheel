def second_largest(nums):
    # Remove duplicates by converting to a set
    unique_nums = set(nums)
    
    # If there are fewer than 2 unique numbers, return None
    if len(unique_nums) < 2:
        return None
    
    # Convert the set back to a list and sort it in descending order
    sorted_unique_nums = sorted(unique_nums, reverse=True)
    
    # Return the second-largest value
    return sorted_unique_nums[1]

# Example usage:
print(second_largest([7, 5, 3, 8, 6]))  # Output: 7
print(second_largest([4, 4, 4, 4]))     # Output: None
print(second_largest([9, 9]))           # Output: None
