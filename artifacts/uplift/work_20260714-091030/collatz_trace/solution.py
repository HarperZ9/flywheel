def collatz_trace(n, limit):
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError('bad start')
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError('bad limit')
    trace = [n]
    steps = 0
    while trace[-1] != 1 and steps < limit:
        steps += 1
        current = trace[-1]
        if current % 2 == 0:
            trace.append(current // 2)
        else:
            trace.append(3 * current + 1)
    if trace[-1] != 1 and steps == limit:
        raise RuntimeError('limit exceeded')
    return trace
