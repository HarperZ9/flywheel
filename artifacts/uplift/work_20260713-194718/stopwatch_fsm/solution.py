def stopwatch(events):
    if not all(isinstance(event, tuple) and len(event) == 2 for event in events):
        raise ValueError('bad event')
    
    total = 0
    laps = []
    previous_time = float('-inf')

    def is_not_running():
        return (event[1] != 'start' or previous_time <= event[0]) and \
               (event[1] != 'stop') and (event[1] != 'reset')
    
    for timestamp, op in events:
        if len(laps) > 0 and not is_not_running():
            raise ValueError('still running')
        
        if timestamp == previous_time:
            raise ValueError('time warp')

        if event[1] == 'start':
            total += timestamp - previous_time if previous_time != float('-inf') else 0
            laps.append(total)
            previous_time = timestamp
        
        elif event[1] == 'stop' and not is_not_running():
            total += timestamp - previous_time

        elif event[1] == 'lap' and not is_not_running():
            total += (timestamp - previous_time) if previous_time != float('-inf') else 0
            laps.append(total)
        
        elif event[1] == 'reset':
            total = 0
            laps.clear()

        previous_time = timestamp
    
    return (total, laps)
