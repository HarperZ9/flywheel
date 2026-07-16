def apportion(weights, total):
    if not all(isinstance(w, int) and w >= 0 for w in weights) or any(w == 0 for w in weights) or not isinstance(total, int) or total < 0:
        raise ValueError("weights must be a non-empty list of non-bool ints, each >= 0 with at least one positive entry; total must be a non-bool int >= 0.")

    s = sum(weights)
    shares = [w * total // s for w in weights]  # Each share starts as the floor of its quota

    remainder = total - sum(shares)  # Total to be distributed among entries with the largest remainders
    sorted_weights_remainders = sorted((w, (w * total) % s) for w in weights)
    
    for _ in range(remainder):
        shares[sorted_weights_remainders[-1][0]] += 1
        del sorted_weights_remainders[-1]
        if not sorted_weights_remainders:
            break

    return shares
