def lru_trace(capacity, ops):
    if not isinstance(capacity, int) or type(capacity) == bool or capacity < 1:
        raise ValueError('bad capacity')
    
    result = []
    cache = {}
    
    for op in ops:
        if len(op) != 2:
            raise ValueError('bad op')
        
        command, key = op
        
        if command == 'get':
            value = cache.get(key, None)
            result.append(value)
            if value is not None:
                cache[key] = (command, key, value)
        elif command == 'put':
            if key in cache:
                cache.pop(key)
            if len(cache) >= capacity:
                _, evicted_key = cache.popitem(last=False)
                
            cache[key] = (command, key, op[1])
    
    return result
