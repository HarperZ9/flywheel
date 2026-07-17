def col_label(n):
    if not isinstance(n, int) or n < 1:
        raise ValueError('bad column')
    label = ''
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        label = chr(65 + remainder) + label
    return label
