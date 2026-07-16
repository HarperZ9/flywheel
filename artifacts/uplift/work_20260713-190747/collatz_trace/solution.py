def collatz_trace(n, limit):
    if not isinstance(n, int) or n < 1:
        raise ValueError('bad start')
    if not isinstance(limit, int) or limit < 0:
        raise ValueError('bad limit')
    
    steps = []
    value = n
    steps.append(value)
    
    while value != 1 and len(steps) - 1 < limit:  # -1 because steps includes the initial n
        if value % 2 == 0:
            value //= 2
        else:
            value = 3 * value + 1
        steps.append(value)
    
    if value != 1:
        raise RuntimeError('limit exceeded')
    
    return steps
