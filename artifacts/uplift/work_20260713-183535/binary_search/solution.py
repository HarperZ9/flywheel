def binary_search(arr, target):
    """
    Perform a binary search on a sorted array to find the index of a specified target value.
    
    Parameters:
    arr (list): A list of elements that is already sorted in ascending order.
    target: The element whose index needs to be found.
    
    Returns:
    int: The index of the target if it exists, otherwise -1.
    """
    left, right = 0, len(arr) - 1
    
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
            
    return -1
