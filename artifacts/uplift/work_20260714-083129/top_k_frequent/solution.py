def top_k(items, k):
    if not isinstance(k, int) or k < 0:
        raise ValueError('bad k')
    distinct_items = {}
    for item in items:
        if not isinstance(item, str):
            raise ValueError('bad item')
        if item in distinct_items:
            distinct_items[item] += 1
        else:
            distinct_items[item] = 1
    
    sorted_items = sorted(distinct_items.keys(), key=lambda x: (-distinct_items[x], x))
    
    if k == 0:
        return []
    else:
        return sorted_items[:k]
