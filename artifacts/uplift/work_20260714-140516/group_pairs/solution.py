def group_pairs(pairs):
    if not isinstance(pairs, list):
        raise ValueError("pairs must be a list")
    result = {}
    for item in pairs:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError("every element must be exactly a (key, value) tuple of length 2")
        key, value = item
        if key not in result:
            result[key] = []
        result[key].append(value)
    return result
