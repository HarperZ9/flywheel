def stopwatch(events):
    if not all(isinstance(event, tuple) and len(event) == 2 for event in events):
        raise ValueError('bad event')
    
    total = 0
    laps = []
    previous_time = None
    
    running = False
    current_segment_start_time = None
    
    for timestamp, op in events:
        if not isinstance(timestamp, int) or isinstance(op, bool):
            raise ValueError('bad event')
        
        if len(events) > 1 and timestamp <= previous_time:
            raise ValueError('time warp')
        
        if not running:
            if op == 'start':
                current_segment_start_time = timestamp
                running = True
            elif op in ['lap', 'stop']:
                raise ValueError('already running')
            elif op in ['reset']:
                total, laps = 0, []
                continue
        else:
            if op == 'start':
                raise ValueError('already running')
            elif op == 'stop':
                elapsed_time = timestamp - current_segment_start_time
                total += elapsed_time
                laps.append(elapsed_time)
                current_segment_start_time = None
            elif op == 'lap':
                laps.append(total - (0 if not laps else laps[-1]))
            elif op == 'reset':
                running, total, laps = False, 0, []
    
    return (total, laps)
