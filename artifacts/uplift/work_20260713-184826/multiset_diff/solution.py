def multiset_diff(a, b):
    from collections import Counter
    
    if any(not isinstance(x, int) for x in a + b):
        raise ValueError('bad item')
    
    c_a = Counter(a)
    c_b = Counter(b)
    
    diff_counts = c_a - c_b
    
    result = []
    for value in sorted(diff_counts.elements()):
        result.extend([value] * diff_counts[value])
        
    return result
