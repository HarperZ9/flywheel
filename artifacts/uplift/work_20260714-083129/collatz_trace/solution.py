def collatz_trace(n: int, limit: int) -> list:
    if not isinstance(n, int) or n < 1:
        raise ValueError('bad start')
    
    if not isinstance(limit, int) or limit < 0:
        raise ValueError('bad limit')
    
    def _collatz_trace_helper(current_value: int, step_count: int) -> None:
        nonlocal steps
        if current_value == 1:
            steps.append(current_value)
            return
        
        # Compute the next value based on whether it's even or odd.
        if current_value % 2 == 0:
            next_value = current_value // 2
        else:
            next_value = 3 * current_value + 1
        
        # If at limit, raise RuntimeError and do not proceed with trace.
        if step_count >= limit:
            raise RuntimeError('limit exceeded')
        
        steps.append(next_value)
        _collatz_trace_helper(next_value, step_count + 1)
    
    steps: list = []
    try:
        _collatz_trace_helper(n, 0)
    except (RuntimeError, ValueError) as e:
        return None
    else:
        return steps
