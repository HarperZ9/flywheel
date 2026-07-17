from collections import Counter


def top_k(items, k):
    if not isinstance(k, int) or isinstance(k, bool):
        raise ValueError("bad k")
    if k < 0:
        raise ValueError("bad k")
    for item in items:
        if not isinstance(item, str):
            raise ValueError("bad item")
    counter = Counter(items)
    ranked = sorted(counter.items(), key=lambda it: (-it[1], it[0]))
    return [s for s, _ in ranked[:k]]
