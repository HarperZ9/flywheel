def stopwatch(events):
    if not events or len(events[0]) != 2 or len(events[-1]) != 2:
        raise ValueError('bad event')
    
    running = False
    total_time = 0
    lap_times = []
    current_total = 0
    
    for i, (timestamp, op) in enumerate(events):
        if timestamp <= events[i-1][0] if i > 0 else False:
            raise ValueError('time warp')
        
        if op == 'start':
            if running:
                raise ValueError('already running')
            running = True
        elif op == 'stop':
            if not running:
                raise ValueError('not running')
            nonlocal total_time, current_total
            total_time += current_total
            running = False
        elif op == 'lap':
            if not running:
                raise ValueError('not running')
            lap_times.append(current_total)
        elif op == 'reset':
            if running:
                raise ValueError('still running')
            total_time = 0
            lap_times.clear()
    
    return (total_time, lap_times)
