def grant_requests(capacity, events):
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("bad capacity")
    if not isinstance(events, list):
        raise ValueError("events must be a list")

    bucket = capacity
    last_ts = -1

    results = []

    for i, event in enumerate(events):
        if len(event) != 2 or type(event[0]) is bool or type(event[1]) is bool:
            raise ValueError(f"bad event at index {i}")
        ts, amount = event
        if not isinstance(ts, int) or not isinstance(amount, int):
            raise ValueError(f"bad event at index {i}: timestamps and amounts must be integers")
        if amount < 1:
            raise ValueError(f"bad event at index {i}: amount must be >= 1")

        if ts < last_ts:
            raise ValueError("time warp")

        elapsed = max(0, ts - last_ts)
        bucket += elapsed
        bucket = min(bucket, capacity)

        granted = (bucket >= amount)
        results.append(granted)

        if granted:
            bucket -= amount

        last_ts = ts

    return results
