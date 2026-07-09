def purge_in_place(items, targets):
    if items is targets:
        raise ValueError("items and targets must be distinct objects")

    def matches(x):
        for t in targets:
            if type(x) is type(t) and x == t:
                return True
        return False

    kept = [x for x in items if not matches(x)]
    removed = len(items) - len(kept)
    items[:] = kept
    return removed
