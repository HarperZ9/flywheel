def uniq_counts(items):
    if not isinstance(items, list):
        raise ValueError('bad input')
    if not items:
        return []
    out = [[items[0], 1]]
    for i in range(1, len(items)):
        if items[i] == items[i - 1] and type(items[i]) is type(items[i - 1]):
            out[-1][1] += 1
        else:
            out.append([items[i], 1])
    return out
