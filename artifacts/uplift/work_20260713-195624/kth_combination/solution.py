import math

def binomial_coefficient(n, k):
    """
    Calculate the binomial coefficient C(n, k).
    
    Args:
        n (int): The total number of items.
        k (int): The number of elements to choose from.
        
    Returns:
        int: Binomial coefficient C(n, k).
    """
    return math.factorial(n) // (math.factorial(k) * math.factorial(n - k))

def kth_combination(n, k, r):
    """
    Generate and sort k-combinations of a list of integers 0...n-1.
    
    Args:
        n (int): The total number of elements in the set.
        k (int): The length of the combination to generate.
        r (int): The desired rank of the generated combination.
        
    Returns:
        List[int]: A sorted list representing a specified k-combination, with elements ordered lexicographically.
    
    Raises:
        ValueError: If n is less than or equal to 0, k is not within the valid range, or r is negative.
        ValueError: If r exceeds C(n, k).
    """
    if n <= 0:
        raise ValueError('n must be a non-negative integer.')
    elif k < 0 or (k != 0 and r < 0):
        raise ValueError('k must be a non-negative integer and rank must be within the valid range.')
    
    # Calculate binomial coefficient
    comb_n_k = binomial_coefficient(n, k)
    
    if r >= n:
        raise ValueError('rank is out of bounds.')
    
    # Generate and sort k-combinations
    kcombs = [sorted(combination) for combination in itertools.combinations(range(n), r)]
    sorted_kcombs = sorted(kcombs)
    
    return sorted_kcombs

# Example usage:
n, k, r = 4, 2, 3
kth_combination(n=5, k=k, r=r)
