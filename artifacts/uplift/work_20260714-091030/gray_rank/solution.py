def gray_rank(bits):
    if not isinstance(bits, str):
        raise ValueError("bad code")
    if not bits:
        raise ValueError("bad code")
    ok = all(c == "0" or c == "1" for c in bits)
    if not ok:
        raise ValueError("bad code")
    n = len(bits)
    idx = int(bits, 2)
    prev = 0
    rank = -1
    limit = 1 << n
    while prev < limit:
        cur = prev ^ (prev >> 1)
        if cur == idx:
            rank = prev
        prev += 1
    return rank
