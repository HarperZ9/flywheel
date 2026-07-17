def k_smallest(records, k):
    if not isinstance(k, int) or k < 0:
        raise ValueError('bad k')
    
    seen_names = set()
    valid_records = []
    
    for record in records:
        if len(record) != 2:
            raise ValueError('bad record')
        
        name, score = record
        
        if not (isinstance(name, str) and isinstance(score, int)):
            raise ValueError('bad record')
        
        if name in seen_names:
            raise ValueError('duplicate name')
        
        valid_records.append((name, score))
        seen_names.add(name)
    
    def compare(x, y):
        return cmp_to_key(lambda x, y: (x[1] > y[1]) or (x[1] == y[1] and x[0] <= y[0]))
    
    valid_records.sort(key=compare)
    
    if k >= len(valid_records):
        return [name for name, _ in valid_records]
    else:
        return [name for name, _ in valid_records[:k]]
