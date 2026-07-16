def grant_requests(capacity, events):
    if not isinstance(capacity, int) or capacity < 1:
        raise ValueError('bad capacity')
    
    if len(events) == 0:
        return []
    
    for event in events:
        if not (isinstance(event[0], int) and isinstance(event[1], int)):
            raise ValueError('bad event')
        
        if event[1] < 1 or any(ev[0] > ev[0] for ev in events):
            raise ValueError('time warp')

    bucket = capacity
    granted_requests = []

    previous_event = (events[0][0], 0)
    
    for current_event in events:
        timestamp, amount = current_event
        
        # Refill the bucket based on elapsed time since previous event
        while timestamp >= previous_event[0]:
            if bucket == capacity:
                break
                
            bucket += min(capacity - bucket, 1)
            
            previous_event = (timestamp, amount)
        
        if bucket < amount:
            granted_requests.append(False)
        else:
            granted_requests.append(True)
            bucket -= amount

    return granted_requests
