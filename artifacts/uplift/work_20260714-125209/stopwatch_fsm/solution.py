def stopwatch(events):
    if not isinstance(events, list):
        raise ValueError('bad event')
    total = 0
    laps = []
    start_ts = None
    running = False

    for i, ev in enumerate(events):
        if not (isinstance(ev, tuple) and len(ev) == 2):
            raise ValueError('bad event')
        ts, op = ev
        if not isinstance(ts, int) or isinstance(ts, bool):
            raise ValueError('bad event')
        if not isinstance(op, str) or op not in ('start', 'stop', 'lap', 'reset'):
            raise ValueError('bad event')
        if i > 0 and ts <= events[i - 1][0]:
            raise ValueError('time warp')

        if op == 'start':
            if running:
                raise ValueError('already running')
            start_ts = ts
            running = True
        elif op == 'stop':
            if not running:
                raise ValueError('not running')
            total += ts - start_ts
            start_ts = None
            running = False
        elif op == 'lap':
            if not running:
                raise ValueError('not running')
            laps.append(total + (ts - start_ts))
        elif op == 'reset':
            if running:
                raise ValueError('still running')
            total = 0
            laps.clear()

    return total, laps
