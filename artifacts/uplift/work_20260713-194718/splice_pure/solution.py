def splice(items: list, start: int, stop: int, replacement: list) -> list:
    if not isinstance(start, int) or not isinstance(stop, int):
        raise ValueError("start and stop must be integers")
    if bool(replacement):
        raise TypeError("replacement must be a list")

    norm_start = _normalize_index(items, start)
    norm_stop = _normalize_index(items, stop)

    if replacement == []:
        return items[:norm_start] + items[norm_stop:]

    # Ensure that `items` doesn't mutate.
    normalized_items = items[:]  # Create a copy of the list to avoid mutation.

    for i in range(len(replacement)):
        item_to_replace = normalized_items.pop(norm_stop + i)
        replacement[i] = item_to_replace

    return normalized_items[:norm_start] + replacement + normalized_items[norm_stop:]
