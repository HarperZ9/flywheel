def kth_combination(n: int, k: int, r: int) -> list:
    if not (0 <= n and isinstance(n, int)):
        raise ValueError("bad n")
    if not (0 <= k and k >= 0):
        raise ValueError("bad k")
    if not (0 <= r < binomial_coefficient(n, k)):
        raise ValueError("bad rank")

    # Placeholder for the actual implementation
    return sorted([0, 1])  # This should be replaced with an actual algorithm

def binomial_coefficient(n: int, k: int) -> int:
    if k == 0 or n == k:
        return 1
    elif k > n:
        return 0
    else:
        # Using the multiplicative formula
        result = 1
        for i in range(1, min(k + 1, n - k) + 1):
            result *= n
            result //= i
            n -= 1
        return result
