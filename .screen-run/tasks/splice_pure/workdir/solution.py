def splice(items, start, stop, replacement):
    def check_index(i):
        if isinstance(i, bool) or not isinstance(i, int):
            raise ValueError("start/stop must be int, not bool/other")

    check_index(start)
    check_index(stop)
    if not isinstance(replacement, list):
        raise TypeError("replacement must be a list")

    n = len(items)

    def norm(i):
        j = i + n if i < 0 else i
        if j < 0:
            j = 0
        if j > n:
            j = n
        return j

    a = norm(start)
    b = norm(stop)
    if b < a:
        b = a
    return items[:a] + list(replacement) + items[b:]
