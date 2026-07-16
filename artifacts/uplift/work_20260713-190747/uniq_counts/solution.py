def uniq_counts(items):
    if not isinstance(items, list):
        raise ValueError('bad input')
    
    if not items:
        return []
    
    result = []
    current_value = items[0]
    count = 1
    
    for i in range(1, len(items)):
        if type(current_value) == type(items[i]) and current_value == items[i]:
            count += 1
        else:
            result.append([current_value, count])
            current_value = items[i]
            count = 1
    result.append([current_value, count])
    
    return result
