def perm_rank(perm):
    if not isinstance(perm, list):
        raise ValueError('bad input')
    
    if any(not isinstance(x, int) for x in perm):
        raise ValueError('bad element')
    
    if len(perm) != len(set(perm)) or min(perm) < 0 or max(perm) >= len(perm):
        raise ValueError('not a permutation')
    
    def factorial(n):
        if n == 0:
            return 1
        else:
            return n * factorial(n-1)
    
    rank = 0
    seen = [False] * len(perm)
    
    for i, val in enumerate(perm):
        seen[val] = True
        numerator = sum(seen[j] for j in range(val))
        fact_n_minus_1 = factorial(len(perm) - 1 - i)
        rank += numerator * fact_n_minus_1
    
    return rank
