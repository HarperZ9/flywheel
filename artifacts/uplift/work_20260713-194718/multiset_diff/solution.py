def multiset_diff(a, b):
    if not all(isinstance(x, int) for x in a + b):
        raise ValueError('bad item')
    
    # Count occurrences of each element in both lists and store them in dictionaries
    from collections import Counter
    count_a = Counter(a)
    count_b = Counter(b)

    # Compute the multiset difference by subtracting counts in 'b' from 'a'
    result_count = {key: value - count_b.get(key, 0) for key, value in count_a.items()}
    
    # Convert dictionary to sorted list
    return sorted(result_count.keys())
