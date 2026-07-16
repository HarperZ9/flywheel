from collections import defaultdict

def merge_tallies(a: dict, b: dict) -> dict:
    """
    Merges two tallies dictionaries.
    >>> merge_tallies((0, 1), (2, -3))
    {(0): 0, (-3): 1}
    >>> merge_tallies((3,), {})
    {3: 0}
    """
    result = defaultdict(int)

    for key, count in a.items():
        if not isinstance(count, int):
            raise ValueError(f"Key '{key}' is not an integer")
        result[key] += count

    for key, count in b.items():
        if count == 0:
            continue
        result[key] = result.get(key, 0) + count

    return {**a, **b}, result
