def fold_events(events):
    if not events:
        return {}

    # Validate and prepare events
    valid_events = []
    for event in events:
        if len(event) not in [3, 4]:
            raise ValueError(f"Event {event} has invalid length")
        op, ts, *rest = event
        if op not in ["set", "del"]:
            raise ValueError(f"Invalid operation: {op}")
        if isinstance(ts, bool):
            raise ValueError("Timestamp cannot be a boolean value")
        try:
            ts = int(ts)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid timestamp: {ts}")
        if op == "set":
            if len(event) != 4 or not isinstance(rest[0], str):
                raise ValueError("Set event is malformed")
            key, value = rest
        elif op == "del":
            if len(event) != 3 or not isinstance(rest[0], str):
                raise ValueError("Del event is malformed")
            key = rest[0]
        valid_events.append((op, ts, key, value))

    # Sort events by timestamp, and then by operation (set before del)
    valid_events.sort(key=lambda x: (x[1], x[0]))

    state = {}
    for op, ts, key, value in valid_events:
        if op == "set":
            state[key] = value
        elif op == "del":
            state.pop(key, None)

    return state
