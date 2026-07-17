def sliding_windows(items, size, step):
    if not isinstance(items, list):
        raise ValueError('bad input')
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ValueError('bad size')
    if not isinstance(step, int) or isinstance(step, bool) or step < 1:
        raise ValueError('bad step')
    result = []
    for i in range(0, len(items) - size + 1, step):
        result.append(items[i:i+size])
    return result
