def purge_in_place(items, targets):
    if items is targets:
        raise ValueError("items and targets are the same object")
    removed = 0
    i = 0
    while i < len(items):
        item_type = type(items[i])
        for target in targets:
            if type(target) is item_type and items[i] == target:
                del items[i]
                removed += 1
                break
        else:
            i += 1
    return removed
