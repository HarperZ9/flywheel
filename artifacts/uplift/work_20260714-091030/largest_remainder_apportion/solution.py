def apportion(weights, total):
    if not isinstance(weights, list) or any(isinstance(w, bool) for w in weights):
        raise ValueError("weights must be a non-empty list of integer weights")
    if len(weights) == 0:
        raise ValueError("weights must be non-empty")
    s = sum(weights)
    if s <= 0:
        raise ValueError("weights must contain at least one positive entry")
    if not isinstance(total, int) or total < 0 or isinstance(total, bool):
        raise ValueError(f"total {total} must be a non-negative integer")
    n = len(weights)

    # Exact quota numerators (integer arithmetic): weights[i] * total
    numerators = [w * total for w in weights]
    # Integer floors sum to floor of the exact quota, by linearity of floor
    shares = [(n // s) for n in numerators]

    # Total so far: sum(shares), exactly equal to sum(floors)
    allocated = sum(shares)
    if allocated == total:
        return list(shares)

    extra = total - allocated

    # Largest-remainder partial quotients (exact): weights[i] * total % s
    remainder_numerators = [(n % s) for n in numerators]
    # Indices sorted by largest remainder, by lower index first on ties
    order = sorted(range(n), key=lambda i: (-remainder_numerators[i], i))

    for _ in range(extra):
        shares[order.pop(0)] += 1

    return list(shares)
