def collatz_trace(n, limit):
    if not isinstance(n, int) or n < 1:
        raise ValueError('bad start')
    
    if not isinstance(limit, int) or limit < 0:
        raise ValueError('bad limit')

    trace = []
    steps = 0
    
    while True:
        trace.append(n)
        steps += 1
        if n == 1:
            break
        
        n = 3 * n + 1 if n % 2 else n // 2

        # Stop tracing if we are past the limit
        if steps > limit:
            raise RuntimeError('limit exceeded')
    
    return trace
