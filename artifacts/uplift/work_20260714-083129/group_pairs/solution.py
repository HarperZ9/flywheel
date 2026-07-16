def group_pairs(pairs):
    if not all(isinstance(pair, tuple) and len(pair) == 2 for pair in pairs):
        raise ValueError("All elements of `pairs` must be exactly two-element tuples.")
    
    result = {}
    seen_keys = set()
    
    for key, value in pairs:
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key not in result:
            result[key] = [value]
        else:
            result[key].append(value)
    
    return result
