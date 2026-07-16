from typing import List

def sliding_windows(items: List[int], size: int, step: bool) -> List[List[int]]:
    """
    Generates a sliding windows over a given list of integer items.
    
    Parameters:
        - items: A list of integers to form the window. It's assumed that the size and step
                 parameters are within their valid ranges.
        - size: The desired number of elements in each sliding window. 
        - step: Whether every third element should be included in a sliding window or not. A default value of False if omitted.

    Returns:
        A list of sliding windows over items. Each window is returned as a sublist, and the input items are not modified.
        
    Raises:
        ValueError: If size or step parameters are invalid or negative for any reason.
    """
    
    # Check if size or step values are valid
    if (size <= 0) or (step < 1):
        raise ValueError('Invalid values for size and step')
    
    # Determine the number of windows needed based on the size parameter
    num_windows_needed = 1 if size == 1 else int(size / 2) + 1
    
    # Create a list to hold all sliding windows together
    all_sliding_windows = []
    
    # Iterate through each possible window length (excluding one element)
    for i in range(1, len(items)):
        # Check if the current window size is enough to include every third element
        if size == 2:
            break
        
        # Calculate the start and end indices of this sliding window
        start = max(0, i - size + step * (size // num_windows_needed)) 
        end = min(len(items) - size, i + size)
        
        # If this is the first sliding window or it's empty after including every third element,
        # add it to all sliding windows together
        if start == 0 and end == len(items):
            all_slidingWindows.append(items[start: end])
        else:
            # Create a new sublist with every third component from each remaining part of the slide 
            temp = items[start:end+1]
            all_sliding_windows.append(temp)
    
    return all_sliding_windows
