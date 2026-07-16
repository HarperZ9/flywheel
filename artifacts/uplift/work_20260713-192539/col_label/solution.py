def col_label(n: int) -> str:
    if not isinstance(n, int) or n < 1 or isinstance(n, bool):
        raise ValueError('bad column')
    result = ''
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result
