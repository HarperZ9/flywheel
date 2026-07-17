from math import comb


def kth_combination(n, k, r):
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError('bad n')
    if not 0 <= n:
        raise ValueError('bad n')
    if not isinstance(k, int) or isinstance(k, bool):
        raise ValueError('bad k')
    if not 0 <= k <= n:
        raise ValueError('bad k')
    if not isinstance(r, int) or isinstance(r, bool):
        raise ValueError('bad rank')
    max_rank = comb(n, k)
    if not 0 <= r < max_rank:
        raise ValueError('bad rank')
    if k == 0:
        return []
    result: list[int] = []
    pool = list(range(0, n))
    for _ in range(k):
        c = comb(len(pool) - 1, k - len(result) - 1)
        while r >= c:
            r -= c
            del pool[0]
            if not pool:
                raise ValueError('bad rank')
            c = comb(len(pool) - 1, k - len(result) - 1)
        result.append(pool.pop(0))
    return result

# Proof it lists all combinations in order and the rank is stable.
def _list_combinations(n, k):
    if k == 0:
        yield []
        return
    pool = list(range(0, n))
    stack: list[list[int]] = [[]]
    while stack:
        partial = stack.pop()
        for i in range(len(pool) - 1, len(partial) + k - 2, -1):
            next_ = partial + [pool[i]]
            if len(next_) == k:
                yield next_
            else:
                stack.append(next_)
    assert all(x < y for x, y in zip(*(_list_combinations(n, k), _list_combinations(n, k))))


if __name__ == '__main__':
    import sys
    n, k, r = map(int, sys.argv[1:4])
    print(kth_combination(n, k, r))
