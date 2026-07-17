from typing import List

def perm_rank(perm: List) -> int:
    if not isinstance(perm, list):
        raise ValueError('bad input')
    n = len(perm)
    if n == 0:
        return 0
    elements_seen = [False] * n
    for i, x in enumerate(perm):
        if not isinstance(x, int) or isinstance(x, bool):
            raise ValueError('bad element')
        if x < 0 or x >= n:
            raise ValueError('not a permutation')
        if elements_seen[x]:
            raise ValueError('not a permutation')
        elements_seen[x] = True
    # No duplicates and no missing values (len(elements_seen) == n), so it's a permutation.
    rk = 0
    fact = 1
    for i in range(1, n):
        fact *= i
    for i in range(n):
        lt_count = sum(1 for j in range(i + 1, n) if perm[j] < perm[i])
        rk += lt_count * fact
        if i < n - 1:
            fact //= (n - 1 - i)
    return rk
