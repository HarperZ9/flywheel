from typing import List

def purge_in_place(items: List[any], targets: List[any]) -> int:
    """
    Removes elements from 'items' whose type matches those in 'targets'.
    
    Args:
        items (List[Any]): The original list to process.
        targets (List[Any]): A target set of elements that should be removed from the 'items' list.
        
    Returns:
        int: The number of elements that were successfully removed, or 0 if no elements are in 'targets'.
    """
    
    count = len(items)
    for item in items:
        # Check if the type of 'item' matches the target
        if isinstance(item, targets[0]) and (isinstance(target[1], type(item)) or (target[1] != item)):
            del items[count]
            count -= 1
    
    return count

# Example check function to verify the solution with provided data points
def check_solution():
    assert purge_in_place([2,4,3,0,1,7,11], [3,5]) == 2
    assert purge_in_place([1,2,3,0,4,1], [2,3]) == 1
    assert purge_in_place([], []) == 0
    print("All tests passed!")

check_solution()
