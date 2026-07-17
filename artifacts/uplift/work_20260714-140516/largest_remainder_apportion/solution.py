def apportion(weights, total):
    if not isinstance(total, int) or not weights or not all(isinstance(w, int) for w in weights):
        raise ValueError("weights must be a non-empty list of ints and total an int")
    if any(not v >= 0 for v in (total,) + tuple(weights)):
        raise ValueError("weights and total must be non-negative")
    if any(isinstance(w, bool) for w in weights + (total,)):
        raise ValueError("weights and total may not be booleans")
    s = sum(weights)
    if not s:
        raise ValueError("weights must contain at least one positive entry")
    floor_share = [(w * total) // s for w in weights]
    remainder = [(w * total - (floor_share[i] * s)) % s for i, w in enumerate(weights)]
    r = total - sum(floor_share)
    if not (0 <= r < len(floor_share)):
        raise ValueError("internal error: remainder count out of bounds")
    extra = sorted(range(len(remainder)), key=lambda i: (-remainder[i], i))[:r]
    for i in extra:
        floor_share[i] += 1
    return tuple(floor_share)
