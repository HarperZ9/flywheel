def multiset_diff(a, b):
    from collections import Counter

    def validate(lst, name):
        if not isinstance(lst, list):
            raise ValueError(f"{name} must be a list")
        for x in lst:
            if not isinstance(x, int) or isinstance(x, bool):
                raise ValueError("bad item")

    validate(a, "a")
    validate(b, "b")

    ca = Counter(a)
    cb = Counter(b)

    result = []
    for value in sorted(set(ca.keys()).union(cb.keys())):
        count = max(0, ca[value] - cb[value])
        result.extend([value] * count)

    return result
