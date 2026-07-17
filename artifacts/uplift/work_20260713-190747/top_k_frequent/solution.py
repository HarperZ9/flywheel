def top_k(items, k):
    if not isinstance(k, int) or isinstance(k, bool) or k < 0:
        raise ValueError('bad k')
    for item in items:
        if not isinstance(item, str):
            raise ValueError('bad item')
    
    from collections import Counter
    counter = Counter(items)
    ranked_items = sorted(counter.items(), key=lambda x: (-x[1], x[0]))
    
    return [item[0] for item in ranked_items[:k]]
