def fold_events(events):
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    
    for event in events:
        if not isinstance(event, tuple):
            raise ValueError(f"event {event!r} is not a tuple")

        if len(event) < 1:
            raise ValueError(f"event {event!r} has no operation")

        op = event[0]
        if op not in ("set", "del"):
            raise ValueError(f"unknown operation: {op!r}")

        if (op == "set" and len(event) != 4) or (op == "del" and len(event) != 3):
            raise ValueError(f"{op!r} event has wrong arity: {event}")
        
        ts = event[1]
        if not isinstance(ts, int) or ts < 0:
            raise ValueError(f"timestamp must be an integer >= 0; got {ts}")

        key = event[2]
        if not isinstance(key, str):
            raise ValueError(f"key must be a string; got {key!r}")   

    # Sort by timestamp (ascending) then by op order at same ts
    events_sorted = sorted(events, key=lambda e: (e[1], ("del", "set").index(e[0]) if len(e) > 2 else 2))

    state = {}
    
    for event in events_sorted:
        op = event[0]
        ts = event[1]

        if op == "set" and len(event) == 4:
            value = event[3] 
            key = event[2]
            # If a future 'del' beats this same set, skip storing it now
            if any(e[0] == "del" and e[1] == ts and e[2] == key for e in events_sorted):
                continue  
            state[key] = value

        elif op == "del":
            # Del at a specific timestamp is processed after all sets, so silent no-op
            pass

    return state
