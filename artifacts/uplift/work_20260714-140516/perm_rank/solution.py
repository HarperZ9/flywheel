from math import factorial


def perm_rank(perm):
    if not isinstance(perm, list):
        raise ValueError('bad input')
    n = len(perm)
    seen = [False] * n
    for x in perm:
        if not isinstance(x, int) or isinstance(x, bool):
            raise ValueError('bad element')
        if 0 <= x < n:
            if seen[x]:
                raise ValueError('not a permutation')
            seen[x] = True
        else:
            raise ValueError('not a permutation')
    if any(not item for item in seen):
        raise ValueError('not a permutation')
    rank = 0
    for i, a in enumerate(perm[:-1]):
        bcount = sum(int(b < a) for b in perm[i + 1 :])
        rank += bcount * factorial(n - i - 1)
    return rank
