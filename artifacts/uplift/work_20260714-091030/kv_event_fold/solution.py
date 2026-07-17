def fold_events(events):
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    
    state = {}
    set_buffer = []
    
    # Parse and validate, collect sets in timestamp order
    for evt in events:
        if not isinstance(evt, tuple):
            raise ValueError(f"event {evt!r} is not a tuple")
        
        op = evt[0] if len(evt) > 0 else None
        
        if op == "set":
            if len(evt) != 4 or \
               not (isinstance(evt[1], int) and isinstance(evt[3], int)):
                raise ValueError(f"invalid set event: {evt!r}")
            ts = evt[1]
            
            # Check for boolean timestamp
            if issubclass(type(ts), bool):
                raise ValueError(f"timestamp must be an integer, got {type(ts).__name__} (bool is not acceptable)")
            
            key = evt[2]
            value = evt[3]
            
            if not isinstance(key, str):
                raise ValueError(f"key in event {evt!r} must be a string")
            
            set_buffer.append((ts, key, value))
        
        elif op == "del":
            if len(evt) != 3 or \
               not (isinstance(evt[1], int)):
                raise ValueError(f"invalid del event: {evt!r}")
            ts = evt[1]
            
            # Check for boolean timestamp
            if issubclass(type(ts), bool):
                raise ValueError(f"timestamp must be an integer, got {type(ts).__name__} (bool is not acceptable)")
            
            key = evt[2]
            
            if not isinstance(key, str):
                raise ValueError(f"key in event {evt!r} must be a string")
            
            # Process del immediately to respect input order
            state.pop(key, None)
        
        else:
            raise ValueError(f"unknown operation: {op!s}")
    
    # Sort sets by timestamp (ascending), keep input order for equal timestamps
    set_buffer.sort()
    
    last_ts = None
    
    for ts, key, value in set_buffer:
        if ts != last_ts:
            last_ts = ts
        
        state[key] = value
    
    return state
