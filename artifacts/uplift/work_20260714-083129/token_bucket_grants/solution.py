def grant_requests(capacity, events):
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError('bad capacity')
    
    bucket = [capacity]
    for i in range(len(events)):
        timestamp, amount = events[i]
        if timestamp < events[i-1][0]:
            raise ValueError('time warp')
        
        # Ensure the event is valid
        if not isinstance(amount, int) or amount < 1:
            raise ValueError('bad event')
        
        while i > 0 and bucket[-1] < (events[i][0] - events[i-1][0]) + 1:
            bucket.append(min(bucket[-1] + 1, capacity))
    
    granted = []
    for timestamp, amount in events:
        if bucket[0] >= amount:
            bucket[0] -= amount
            granted.append(True)
        else:
            granted.append(False)
    
    return granted
