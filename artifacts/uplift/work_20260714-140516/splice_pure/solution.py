def splice(items, start: int, stop: int, replacement) -> list:
    if not isinstance(start, int) or isinstance(start, bool):
        raise ValueError("start must be an integer")
    if not isinstance(stop, int) or isinstance(stop, bool):
        raise ValueError("stop must be an integer")
    if not isinstance(replacement, list):
        raise TypeError("replacement must be a list")

    n = len(items)
    start = max(0, min(n, start + (n if start < 0 else 0)))
    stop = max(0, min(n, stop + (n if stop < 0 else 0)))

    return items[:start] + replacement + items[stop:]
