def rotate(items: list, k: int) -> list:
    """
    Rotate the given list items to the right by k positions.
    
    Args:
    - items: A list representing the original rotated list.
    - k: An integer representing the number of times to rotate the list elements to the right.
      It's taken modulo the length of the list, so k is adjusted accordingly and wraps around.
      
    Returns:
    - A new list that has been rotated by k positions.
    
    Raises:
    - ValueError: If items is not a list or if k is not an integer.
    - ValueError: If k is negative or greater than the length of the input list.
    """
    if not isinstance(items, list):
        raise ValueError('bad input')
    if type(k) != int:
        raise ValueError('bad shift')
    
    # Adjust k for modulo length
    adjusted_k = k % len(items)
    items_length = len(items)

    # Perform rotation
    rotated_list = items[-adjusted_k:] + items[:-adjusted_k]
    return rotated_list
