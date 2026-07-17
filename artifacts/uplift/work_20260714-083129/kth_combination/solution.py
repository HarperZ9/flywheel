def kth_combination(n: int, k: int, r: int) -> list:
    if not (0 <= k <= n):
        raise ValueError('bad k')
    
    if not (0 <= r < binomial_coefficient(n, k)):
        raise ValueError('bad rank')
    
    result = []
    candidates = [i for i in range(n)]
    
    def _kth_combination(index: int, combination: list):
        if len(combination) == k:
            sorted_combination = tuple(sorted(combination))
            result.append(sorted_combination)
            return
        for i, candidate in enumerate(candidates):
            _kth_combination(index + 1, combination + [candidate])
    
    _kth_combination(0, [])
    return list(result[0])
