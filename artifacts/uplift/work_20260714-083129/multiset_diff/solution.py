def multiset_diff(a, b):
    if any(not isinstance(i, int) for i in a + b):
        raise ValueError('bad item')
    
    count_a = {}
    count_b = {}
    
    for item in a:
        count_a[item] = count_a.get(item, 0) + 1
    
    for item in b:
        if item not in count_a:
            continue
        count_b[item] = count_b.get(item, 0) + 1
    
    result = []
    
    for item, count in count_a.items():
        if item in count_b and count > count_b[item]:
            continue
        else:
            result.append(item * (count - count_b.get(item, 0)))
    
    return sorted(result)
