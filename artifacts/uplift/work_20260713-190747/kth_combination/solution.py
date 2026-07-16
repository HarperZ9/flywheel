def kth_combination(n, k, r):
    if not isinstance(n, int) or n < 0:
        raise ValueError('bad n')
    if not isinstance(k, int) or k < 0 or k > n:
        raise ValueError('bad k')
    if not isinstance(r, int) or r < 0 or r >= binomial_coefficient(n, k):
        raise ValueError('bad rank')

    def binomial_coefficient(n, k):
        result = 1
        for i in range(k):
            result *= n - i
            result //= i + 1
        return result

    combination = []
    remaining = [True] * (n - k) + [False] * k
    for i in range(n):
        if r == binomial_coefficient(n - i - 1, k - len(combination)):
            combination.append(i)
            for j in range(len(remaining)):
                remaining[j] = False
        else:
            r -= binomial_coefficient(n - i - 1, k - len(combination))

    return sorted(combination)
