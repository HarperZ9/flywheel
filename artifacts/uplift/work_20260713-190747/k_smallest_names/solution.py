def k_smallest(records, k):
    if not isinstance(k, int) or k < 0:
        raise ValueError('bad k')
    
    valid_records = []
    name_set = set()
    
    for record in records:
        if not (isinstance(record, tuple) and len(record) == 2):
            raise ValueError('bad record')
        
        name, score = record
        if not (isinstance(name, str) and isinstance(score, int)):
            raise ValueError('bad record')
        
        if name in name_set:
            raise ValueError('duplicate name')
        
        valid_records.append((name, score))
        name_set.add(name)
    
    # Sort by score then name
    sorted_records = sorted(valid_records, key=lambda x: (x[1], x[0]))
    
    return [record[0] for record in sorted_records[:k]]
