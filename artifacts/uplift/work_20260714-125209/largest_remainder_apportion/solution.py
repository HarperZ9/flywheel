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
    floored = [(w * total) // s for w in weights]
    remainders = [(w * total) % s for w in weights]
    excess = total - sum(floored)
    # largest remainder first, then lower index; stable sort since python sorts
    # tuples by element lexicographically and we only care about the first
    sorted_indices = sorted(range(len(weights)), key=lambda i: (remainders[i], -i), reverse=True)[:excess]
    for i in sorted_indices:
        floored[i] += 1
    return floored
