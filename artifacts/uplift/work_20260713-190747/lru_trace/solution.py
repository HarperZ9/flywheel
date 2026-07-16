def lru_trace(capacity, ops):
    if not isinstance(capacity, int) or bool(capacity) or capacity < 1:
        raise ValueError('bad capacity')
    
    cache = {}
    result = []
    from collections import deque
    
    def evict():
        key_to_evict = least_recent_order.popleft()
        del cache[key_to_evict]
    
    least_recent_order = deque()
    
    for op in ops:
        if len(op) != 2 and len(op) != 3:
            raise ValueError('bad op')
        
        if op[0] == 'get':
            key = op[1]
            if key in cache:
                result.append(cache[key])
                least_recent_order.remove(key)
                least_recent_order.append(key)
            else:
                result.append(None)
        elif op[0] == 'put':
            key, value = op[1], op[2]
            if key in cache:
                cache[key] = value
                least_recent_order.remove(key)
                least_recent_order.append(key)
            else:
                if len(cache) == capacity:
                    evict()
                cache[key] = value
                least_recent_order.append(key)
        else:
            raise ValueError('bad op')
    
    return result
