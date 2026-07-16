def splice(items, start, stop, replacement):
    if not isinstance(start, int) or not isinstance(stop, int):
        raise ValueError("start and stop must be integers")
    
    if isinstance(replacement, bool):
        raise TypeError("replacement cannot be a boolean")
    
    if not isinstance(replacement, list):
        raise TypeError("replacement must be a list")

    normalized_start = start + len(items) if start < 0 else max(0, min(start, len(items)))
    normalized_stop = stop + len(items) if stop < 0 else max(0, min(stop, len(items)))

    if normalized_start >= normalized_stop:
        return items[:normalized_start] + replacement

    new_items = items[:normalized_start]
    for i in reversed(range(normalized_start, normalized_stop)):
        new_items.append(items[i])
    
    for item in replacement:
        new_items.insert(normalized_start, item)
    
    return new_items
