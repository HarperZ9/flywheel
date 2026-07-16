def purge_in_place(items, targets):
    if items is targets:
        raise ValueError("items and targets cannot be the same object")

    to_remove = [type(t) for t in targets]  # types of elements to remove

    remove_count = 0
    i = 0
    while i < len(items):
        if type(items[i]) in to_remove and items[i] in targets:
            del items[i]
            remove_count += 1
        else:
            i += 1

    return remove_count
