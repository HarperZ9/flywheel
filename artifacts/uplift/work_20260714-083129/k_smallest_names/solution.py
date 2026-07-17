def k_smallest(records, k):
    if not isinstance(k, int) or k < 0:
        raise ValueError('bad k')
    
    name_to_score = {}
    seen_names = set()
    
    for record in records:
        if len(record) != 2:
            raise ValueError('bad record')
        
        name, score = record
        if not isinstance(name, str) or not isinstance(score, int):
            raise ValueError('bad record')
        
        if name in seen_names:
            raise ValueError('duplicate name')
        
        name_to_score[name] = (score, len(seen_names))
        seen_names.add(name)
    
    records_by_rank = sorted(name_to_score.items(), key=lambda x: (x[1][0], x[0]))
    
    result = [name for name, _ in records_by_rank[:k]]
    
    return result
