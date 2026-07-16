def col_label(n):
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("bad column")
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s
