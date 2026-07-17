def collatz_trace(n, limit):
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError('bad start')
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError('bad limit')
    trace = [n]
    steps = 0
    while trace[-1] != 1 and steps < limit:
        value = trace[-1]
        next_value = value // 2 if value % 2 == 0 else 3 * value + 1
        trace.append(next_value)
        steps += 1
    if trace[-1] != 1:
        raise RuntimeError('limit exceeded')
    return trace
