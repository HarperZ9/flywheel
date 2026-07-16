def lru_trace(capacity, ops):
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError('bad capacity')
    cache = {}
    order = []
    results = []
    for op in ops:
        if not isinstance(op, tuple):
            raise ValueError('bad op')
        cmd = op[0]
        if cmd == 'get':
            if len(op) != 2 or not isinstance(op[1], str):
                raise ValueError('bad op')
            key = op[1]
            results.append(cache.get(key))
            if key in cache:
                order.remove(key)
                order.append(key)
        elif cmd == 'put':
            if len(op) != 3 or not isinstance(op[1], str):
                raise ValueError('bad op')
            key, value = op[1], op[2]
            if key in cache:
                order.remove(key)
            else:
                while len(cache) >= capacity:
                    del cache[order.pop(0)]
            cache[key] = value
            order.append(key)
        else:
            raise ValueError('bad op')
    return results
