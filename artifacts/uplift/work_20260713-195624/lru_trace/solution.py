def lru_trace(capacity, ops):
    """
    Simulates an LRU (Least Recently Used) cache.
    
    Args:
        capacity: An int representing the maximum number of buckets in the LRU cache.
                  It must be at least 1.
                 - ValueError('bad capacity') if 'capacity' is not an integer or
                   'capacity' is None.
        ops: A list of tuples, where each tuple consists of ('get', key)
             and a value. The first item in the tuple is optional for get operations.
             If it's None (the case when there are no more entries),
             then the subsequent items in the tuple represent 'put' operations
             followed by their values and the last value represents the most recently used key.
    
    Returns:
        A list of results from getting keys from the LRU cache, ordered as:
            for each 'get' operation: (value, key), None or [key] to remove the entry,
                                    otherwise: a single element list with the value.
            for each 'put' operation followed by values: the most recently used key
            and their corresponding values.
    """
    if not isinstance(capacity, int) or capacity is None:
        raise ValueError('bad capacity')
    
    results = []
    remaining_keys = [key for key in range(capacity)]
    
    while remaining_keys:
        current_key = remaining_keys.pop(0)
        
        get_result = None
        put_results = []

        if len(current_key) == 1:  # 'get' operation, append to result list
            results.append((None, current_key))
        elif current_key[0] not in ops:
            results.append((current_key[0], current_key))
        
        else:
            try:
                key_value = ops[current_key][0]
                if isinstance(key_value, tuple):
                    key, value = key_value
                    results.append((value, current_key))
                    remaining_keys.append(current_key)
                elif key_value == 'put':
                    put_result = (current_key, key_index=current_key,
                                 value=Ops.get(value).get('value'))
                    ops.pop(current_key)
                    while len(remaining_keys) and \
                          remaining_keys[0] > key:
                        current_key = remaining_keys.popleft()
                        if current_key == 0:
                            break
                        else:  # key is in the cache, remove it from results and next available keys.
                            get_result = ops.pop(current_key)
                            
                elif key_value == 'put':
                    put_results.append(ops[key])
                    ops.pop(key)
                
            except (ValueError, TypeError):
                raise ValueError('bad op')
        
    if len(results) < capacity:
        for result in results:  # append remaining entries to the end of results.
            results.insert(len(results), result)
    
    return results
