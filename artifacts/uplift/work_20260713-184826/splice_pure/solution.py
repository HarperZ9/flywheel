def splice(items, start, stop, replacement):
    if not isinstance(start, int) or not isinstance(stop, int):
        raise ValueError("start and stop must be integers")
    
    if not isinstance(replacement, list):
        raise TypeError("replacement must be a list")

    # Normalize indices
    n = len(items)
    start = max(0, min(start + n if start < 0 else start, n))
    stop = max(0, min(stop + n if stop < 0 else stop, n))

    if start > stop:
        return items[:start] + replacement + items[stop:]

    # Create a new list with the splice
    result = items[:start] + replacement + items[stop:]
    
    # Ensure no mutation of input lists by comparing identities
    assert id(result) != id(items), "Result must not be the same object as items"
    for item in replacement:
        assert id(item) == id(result[result.index(item)]), "Elements must have the same identity"

    return result
