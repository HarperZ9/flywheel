def apportion(weights, total):
    if not all(isinstance(w, int) for w in weights) or any(isinstance(w, bool) for w in weights):
        raise ValueError("weights must consist of non-bool integers only.")
    if any(w < 0 for w in weights):
        raise ValueError("All elements in weights must be >= 0.")
    if not weights:
        raise ValueError("weights must be a non-empty list.")
    
    s = sum(weights)
    if s == 0:
        return [total] * len(weights)  # Special case where all shares are equal
    
    if not isinstance(total, int) or total < 0:
        raise ValueError("Total must be a non-negative integer.")

    # Calculate initial shares
    shares = [(w * total) // s for w in weights]
    
    # Calculate remainders and find the number of extra units to distribute
    remainders = [((w * total) % s, i) for i, w in enumerate(weights)]
    r = total - sum(shares)
    
    # Distribute remaining units based on largest remainder method
    remainders.sort(reverse=True)  # Sort by remainder value and index (in reverse order to get LARGEST first)
    for _ in range(r):
        _, index = remainders.pop()
        shares[index] += 1
    
    return shares
