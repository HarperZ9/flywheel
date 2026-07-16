def perm_rank(perm):
    def factorial(n):
        if n == 0:
            return 1
        else:
            return n * factorial(n - 1)
    
    # List check: ensure all elements are in the list and unique
    if set(perm) != set(range(len(perm))):
        raise ValueError('not a permutation')
    
    # Element type check: ensure all elements are integers
    if not all(isinstance(x, int) for x in perm):
        raise ValueError('bad element')
    
    rank = 0
    factorial_n = factorial(len(perm))
    
    for i, val in enumerate(perm):
        count = 0
        for j in range(i + 1, len(perm)):
            if perm[j] < val:
                count += 1
        rank += factorial_n // factorial(i + 1 - count) * count
    
    return rank
