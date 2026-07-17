def group_pairs(pairs):
    if not all(isinstance(pair, tuple) and len(pair) == 2 for pair in pairs):
        raise ValueError("Each element in 'pairs' must be exactly a tuple of length 2")
    
    result = {}
    for key, value in pairs:
        if key not in result:
            result[key] = []
        result[key].append(value)
    
    return result
