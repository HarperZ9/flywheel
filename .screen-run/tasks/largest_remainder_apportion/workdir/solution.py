def apportion(weights, total):
    if isinstance(total, bool) or not isinstance(total, int):
        raise ValueError("total must be a non-bool int")
    if total < 0:
        raise ValueError("total must be >= 0")
    if not isinstance(weights, list) or len(weights) == 0:
        raise ValueError("weights must be a non-empty list")
    for w in weights:
        if isinstance(w, bool) or not isinstance(w, int):
            raise ValueError("weights must be non-bool ints")
        if w < 0:
            raise ValueError("weights must be >= 0")
    s = sum(weights)
    if s == 0:
        raise ValueError("at least one weight must be positive")
    floors = [(w * total) // s for w in weights]
    rems = [(w * total) % s for w in weights]
    r = total - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: (-rems[i], i))
    result = list(floors)
    for i in order[:r]:
        result[i] += 1
    return result
