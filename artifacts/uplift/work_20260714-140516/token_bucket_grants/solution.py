def grant_requests(capacity, events):
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError('bad capacity')
    if not isinstance(events, list):
        raise ValueError('bad event')
    last = None
    bucket = capacity
    out = []
    for e in events:
        if not (isinstance(e, tuple) and len(e) == 2):
            raise ValueError('bad event')
        t, a = e
        if isinstance(t, bool) or isinstance(a, bool):
            raise ValueError('bad event')
        if not (isinstance(t, int) and isinstance(a, int)):
            raise ValueError('bad event')
        if a < 1:
            raise ValueError('bad event')
        if last is not None and t < last:
            raise ValueError('time warp')
        if last is not None:
            bucket += t - last
            bucket = min(bucket, capacity)
        granted = (bucket >= a) if capacity != 0 else False
        out.append(granted)
        if granted:
            bucket -= a
        last = t
    return out
