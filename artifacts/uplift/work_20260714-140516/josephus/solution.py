def josephus(n: int, k: int) -> int:
    if n < 1 or k < 1:
        raise ValueError("n and k must be >= 1")
    remaining = list(range(n))
    index = 0
    while len(remaining) > 1:
        index = (index + k - 1) % len(remaining)
        del remaining[index]
    return remaining[0]
