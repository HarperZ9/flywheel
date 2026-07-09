def josephus(n, k):
    if n < 1 or k < 1:
        raise ValueError((n, k))
    pos = 0
    for m in range(2, n + 1):
        pos = (pos + k) % m
    return pos
