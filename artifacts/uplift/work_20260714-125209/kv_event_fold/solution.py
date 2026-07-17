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
        if not isinstance(ts, int) or isinstance(ts, bool):
            raise ValueError(f"timestamp must be integer >= 0; got: {ts}")

        key = event[2]
        if not isinstance(key, str):
            raise ValueError(f"key must be a string; got: {key!r}")

    # Sort by timestamp ascending. Sets first within each ts so the later
    # (in input order) set wins for equal keys.
    events.sort(key=lambda e: (e[1], 0 if e[0] == "set" else 1))

    state = {}
    last_ts = -1
    for event in events:
        op, ts, key = event[:3]
        if len(event) > 3:
            value = event[3]

        assert isinstance(ts, int)

        # Flush any pending deletes from up to, but not including this ts.
        if ts != last_ts:
            keys_to_delete = [k for k in state
                              if (state[k][1] < ts and
                                  (op == "del" or key != k))]
            for k in keys_to_delete:
                del state[k]
            last_ts = ts

        if op == "del":
            continue
        
        # op == "set"; value is guaranteed by the event shape check above.
        assert len(event) > 3
        state[key] = (value, ts)

    return {k: v[0] for k, v in state.items()}
