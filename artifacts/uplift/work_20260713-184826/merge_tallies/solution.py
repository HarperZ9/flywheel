def merge_tallies(a, b):
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in a.values()) or \
       not all(isinstance(v, int) and not isinstance(v, bool) for v in b.values()):
        raise ValueError("All values must be integers and not booleans")

    merged = {}
    # Process keys from a
    for key in a:
        if key in a and key in b:
            merged[key] = a[key] + b[key]
        elif key in a:
            merged[key] = a[key]

    # Process keys from b
    for key in b:
        if key not in a:  # Avoid duplicates processed from 'a'
            if key in b and (key not in merged or merged[key] == 0):
                merged[key] = b[key]

    # Remove keys with count of 0
    merged = {k: v for k, v in merged.items() if v != 0}

    return merged
