def fold_events(events):
    arity = {"set": 4, "del": 3}
    for ev in events:
        if not isinstance(ev, tuple):
            raise ValueError("event must be a tuple")
        if len(ev) < 1 or ev[0] not in arity:
            raise ValueError("unknown op")
        if len(ev) != arity[ev[0]]:
            raise ValueError("bad arity")
        ts = ev[1]
        if isinstance(ts, bool) or not isinstance(ts, int) or ts < 0:
            raise ValueError("bad timestamp")
        if not isinstance(ev[2], str):
            raise ValueError("bad key")
    order = sorted(
        range(len(events)),
        key=lambda i: (events[i][1], 0 if events[i][0] == "set" else 1, i),
    )
    state = {}
    for i in order:
        ev = events[i]
        if ev[0] == "set":
            state[ev[2]] = ev[3]
        else:
            state.pop(ev[2], None)
    return state
