def grant_requests(capacity, events):
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError('bad capacity')
    if not isinstance(events, list):
        raise ValueError('bad event')
    last_t = None
    bucket = capacity
    out = []
    for ev in events:
        if not (isinstance(ev, tuple) and len(ev) == 2):
            raise ValueError('bad event')
        t, a = ev
        if not (isinstance(t, int) and isinstance(a, int)):
            raise ValueError('bad event')
        if last_t is not None and t < last_t:
            raise ValueError('time warp')
        if a < 1:
            raise ValueError('bad event')
        if last_t is not None:
            bucket += min(capacity - bucket, t - last_t)
        granted = (bucket >= a)
        out.append(granted)
        if granted:
            bucket -= a
        last_t = t
    return out
