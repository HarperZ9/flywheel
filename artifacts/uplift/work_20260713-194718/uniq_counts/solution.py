def uniq_counts(items):
    if not isinstance(items, list):
        raise ValueError('bad input')
    
    result = []
    if items:
        current_value = items[0]
        count = 1
        
        for i in range(1, len(items)):
            if items[i] == current_value and type(current_value) == type(items[i]):
                count += 1
            else:
                result.append([current_value, count])
                current_value = items[i]
                count = 1
        
        # Append the last run
        result.append([current_value, count])
    
    return result
