def purge_in_place(items, targets):
    if items is targets:
        raise ValueError("items cannot be the same object as targets")

    num_removed = 0
    for i in range(len(items)):
        if items[i] in targets and type(items[i]) is type(targets[0]):
            del items[i]
            num_removed += 1
            # Prevent index shifting after deletion
            i -= 1

    return num_removed
