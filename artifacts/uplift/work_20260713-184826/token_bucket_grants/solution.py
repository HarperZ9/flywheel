def grant_requests(capacity, events):
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError('bad capacity')
    
    for i, event in enumerate(events):
        if not (isinstance(event, tuple) and len(event) == 2 and all(isinstance(v, int) and v >= 0 for v in event)):
            raise ValueError('bad event')
        if i > 0 and event[0] < events[i-1][0]:
            raise ValueError('time warp')

    timeline = []
    bucket_capacity = capacity
    granted = []

    for timestamp, amount in events:
        elapsed_time = timestamp - (timeline[-1][0] if timeline else 0)
        refill = min(elapsed_time, bucket_capacity - (bucket_capacity := max(bucket_capacity - amount, 0)))
        if bucket_capacity >= amount:
            granted.append(True)
            bucket_capacity -= amount
        else:
            granted.append(False)
        timeline.append((timestamp, bucket_capacity))

    return granted
