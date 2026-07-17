def lru_trace(capacity, ops):
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError('bad capacity')
    cache = {}
    order = []
    result = []
    for op in ops:
        if (
            not isinstance(op, tuple)
            or (op[0] == 'get' and len(op) != 2)
            or (op[0] == 'put' and len(op) != 3)
            or op[0] not in {'get', 'put'}
        ):
            raise ValueError('bad op')
        if op[0] == 'get':
            key = op[1]
            result.append(cache.get(key))
            if key in cache:
                order.remove(key)
                order.append(key)
        else:
            key, value = op[1], op[2]
            if key in cache:
                cache[key] = value
                order.remove(key)
                order.append(key)
            elif len(order) == capacity:
                evict = order.pop(0)
                del cache[evict]
                cache[key] = value
                order.append(key)
            else:
                cache[key] = value
                order.append(key)
    return result
