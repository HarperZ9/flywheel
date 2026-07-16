def group_pairs(pairs):
    if not all(isinstance(pair, tuple) and len(pair) == 2 for pair in pairs):
        raise ValueError("All elements in pairs must be exactly two-tuples.")
    
    result = {}
    for key, value in pairs:
        if key in result:
            result[key].append(value)
        else:
            result[key] = [value]
    return result
