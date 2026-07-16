from typing import List

def multiset_diff(a: List[int], b: List[int]) -> List[int]:
    """
    Returns the multiset difference between two sets of integers, a and b.
    
    Parameters:
    a (List[int]): The first set of elements.
    b (List[int]): The second set of elements.
    
    Returns:
    List[int]: A sorted list containing elements from both a and b. Each distinct value
                has its count proportional to the difference in their occurrences between a
                and b. Duplicate values are ignored.
    """
    # Dictionary to keep track of counts for each unique element
    counts_dict = {}
    
    # Counting occurrences in set a
    for num in a:
        if num not in counts_dict:
            counts_dict[num] = 0
    
    # Counting occurrences in set b
    for num in b:
        if num not in counts_dict:
            counts_dict[num] = 1
    
    # Updating the counts to maintain the order and count of each unique element
    for key, value in counts_dict.items():
        key_count = a.count(key)
        if key_count * (len(a) - key_count) < len(b):
            counts_dict[key] += value * (len(a) - key_count)
    
    # Reconstructing the multiset differences and sorting them
    result = []
    for num in sorted(counts_dict.keys()):
        key_count = a.count(num)
        if key_count * (len(a) - key_count) < len(b):
            count_diff = b.count(num)
            difference = key_count * count_diff - value
        else:
            difference = abs(key_count - 1)
        
        result.append(difference)
    
    return result

# Function to check the correctness of the solution
def check_solution():
    a = [4, 3, 2]
    b = [2, 1, 0, 4]
    expected_outcome = [-2, -1, 0, -1, 4, 9]
    
    outcome = multiset_diff(a, b)
    assert outcome == expected_outcome, f"Expected {expected_outcome}, but got {outcome}"
    print("Solution is correct.")

check_solution()
