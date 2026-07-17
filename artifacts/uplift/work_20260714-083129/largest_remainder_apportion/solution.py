def apportion(weights, total):
    if not all(isinstance(x, int) for x in weights) or any(x < 0 for x in weights):
        raise ValueError("weights must be a non-empty list of non-negative integers with at least one positive entry.")
    
    s = sum(weights)
    
    shares = []
    remainder_distribution = [x * total % s for x in weights]
    remainder_distribution.sort(reverse=True)
    
    for i, weight in enumerate(weights):
        share = (weight * total) // s
        if i < len(remainder_distribution) and remainder_distribution[i] == 0:
            share += 1
        
        shares.append(share)
        
        if len(shares) != len(weights):
            total -= share
    
    total_sum = sum(shares)
    
    if total_sum != total:
        raise ValueError("The returned list must sum to exactly the total.")
    
    return shares
