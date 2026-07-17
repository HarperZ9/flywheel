from typing import List

def multiset_diff(a: List[int], b: List[int]) -> List[int]:
    """
    Calculate the multiset difference between two lists a and b.
    Each element in both lists must be an int (not bool) and of different types,
    or the function will raise a ValueError. The result is sorted as per your requirements.

    >>> multiset_diff([], [])
    []
    >>> multiset_diff([1, 2], [3])
    [4]
    >>> multiset_diff([-7, -8], [0, -9, -10])
    [-8, -7]
    """
    if not a or not b:
        raise ValueError('Both lists must contain at least one element.')
    
    # Convert both lists to hash sets for easier comparison and extraction of values
    set_a = {a}
    set_b = {b}
    
    # Find common elements between the two sets
    common_items = set_a.intersection(set_b)
    
    # Calculate the multiset difference
    result = [value - count if count > 0 else value for value, count in zip(common_items, len(common_items))]
    
    return sorted(result)

# Function to check the correctness of the solution
def check_solution():
    assert multiset_diff([], []) == []
    assert multiset_diff([1, 2], [3]) == [4]
    assert multiset_diff([-7, -8], [0, -9, -10]) == [-8, -7]
    print("All tests passed!")

# Run the check function to verify the solution
check_solution()
