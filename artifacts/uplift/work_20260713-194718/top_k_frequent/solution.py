def top_k(items: list, k: int) -> list:
    if not isinstance(k, int):
        raise ValueError('bad k')
    if k < 0:
        raise ValueError('bad k')

    from collections import Counter
    distinct_items = sorted(set([item for item in items if isinstance(item, str)]), key=lambda x: (-Counter(items)[x], x))
    
    return distinct_items[:k]
