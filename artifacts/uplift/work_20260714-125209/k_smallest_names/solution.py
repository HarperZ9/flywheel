def k_smallest(records, k):
    if not isinstance(k, int) or isinstance(k, bool):
        raise ValueError('bad k')
    if k < 0:
        raise ValueError('bad k')

    seen = set()
    ranked = []

    for record in records:
        if not isinstance(record, tuple) or len(record) != 2:
            raise ValueError('bad record')
        name, score = record
        if not isinstance(name, str):
            raise ValueError('bad record')
        if not isinstance(score, int) or isinstance(score, bool):
            raise ValueError('bad record')
        if name in seen:
            raise ValueError('duplicate name')
        seen.add(name)
        ranked.append((score, name))

    ranked.sort()
    return [name for _, name in ranked[:k]]
