from math import comb

def kth_combination(n, k, r):
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError("bad n")
    if not isinstance(k, int) or isinstance(k, bool) or k < 0 or k > n:
        raise ValueError("bad k")
    total = comb(n, k)
    if not isinstance(r, int) or isinstance(r, bool) or r < 0 or r >= total:
        raise ValueError("bad rank")
    result = []
    available = list(range(n))
    for _ in range(k):
        chosen = None
        for x in available:
            left = comb(x + n - len(available) - 1, k - len(result) - 1)
            if r >= left:
                r -= left
            else:
                chosen = x
                break
        result.append(chosen)
        available.remove(chosen)
    return result
