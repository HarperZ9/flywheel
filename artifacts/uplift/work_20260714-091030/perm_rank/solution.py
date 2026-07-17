from math import factorial


def perm_rank(perm):
    if not isinstance(perm, list):
        raise ValueError('bad input')
    n = len(perm)
    seen = [False] * n
    for x in perm:
        if not isinstance(x, int) or isinstance(x, bool):
            raise ValueError('bad element')
        if x < 0 or x >= n:
            raise ValueError('not a permutation')
        seen[x] = True
    if any(not s for s in seen):
        raise ValueError('not a permutation')

    rank = 0
    left = list(range(n))
    for i, p in enumerate(perm):
        c = sum(1 for x in left[:p])
        rank += c * factorial(n - i - 1)
        del left[p]
    return rank
