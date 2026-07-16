def sliding_window_max(nums, k):
    if k <= 0:
        raise ValueError("Window size k must be positive.")
    if k > len(nums):
        return []
    
    maxes = []
    window = nums[:k]
    for i in range(k, len(nums)):
        current_max = max(window)
        maxes.append(current_max)
        
        # Update the window
        window.pop(0)  # Remove the first element (oldest one)
        window.append(nums[i])
    
    # Add the last window's maximum as the final result
    maxes.append(max(window))
    return maxes
