def flatten_nested(lst):
    """
    Flattens an arbitrarily nested list of integers into a single flat list,
    preserving the original order.
    
    Example:
    >>> flatten_nested([1, [2, 3], 4])
    [1, 2, 3, 4]
    """
    result = []
    for item in lst:
        if isinstance(item, list):
            # Recursively flatten the sublist
            result.extend(flatten_nested(item))
        else:
            # Add the current item to the result list
            result.append(item)
    return result
