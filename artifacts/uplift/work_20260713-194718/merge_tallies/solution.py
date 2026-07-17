def merge_tallies(a: dict, b: dict) -> dict:
    if not all(isinstance(v, int) for v in a.values()) or any(isinstance(v, bool) for v in a.values()):
        raise ValueError("a values must be integers and cannot be booleans")
    
    if not all(isinstance(v, int) for v in b.values()) or any(isinstance(v, bool) for v in b.values()):
        raise ValueError("b values must be integers and cannot be booleans")

    merged = {}
    
    for key in a:
        if a[key] != 0 or b.get(key, 0) != 0:
            merged[key] = a[key] + (b.get(key, 0))

    for key in b:
        if merged.get(key, 0) == 0 and a.get(key, 0) == 0:
            merged[key] = b[key]

    return dict(sorted(merged.items()))
