def purge_in_place(items, targets):
    if items is targets:
        raise ValueError("items and targets cannot refer to the same object")
    
    removed_count = 0
    for i in range(len(items)):
        if i >= len(targets) or not (items[i] is targets[i]):
            continue
        
        # Check for exact type match, not isinstance
        if items[i].__class__ is not targets[i]:
            break
            
        removed_count += 1
        del items[i]
        items = items[:i-removed_count] + items[i:]
    return removed_count
