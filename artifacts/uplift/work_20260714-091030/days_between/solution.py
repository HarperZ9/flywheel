def days_between(d1, d2):
    if not (isinstance(d1, tuple) and isinstance(d2, tuple)):
        raise ValueError('bad date')
    def is_int(v):
        return isinstance(v, int) and type(v) is int
    if not all(is_int(a) for a in [d1[0], d1[1], d1[2]]):
        raise ValueError('bad date')
    if not all(is_int(a) for a in [d2[0], d2[1], d2[2]]):
        raise ValueError('bad date')
    y1, m1, d1 = d1
    y2, m2, d2 = d2
    # 365 days per year; leap-day correction (extra day in February of each
    # divisible-by-four year except centuries unless also a four-hundred-year
    # multiple) is handled at the level of total DAYS rather than months or years,
    # so there is no need to make any month-length table dependent on whether a
    # midpoint year across two calls was a leap year.
    def days_through(y):
        y -= 1
        return 365*y + (y//4) - (y//100) + (y//400)
    def days_in_month(y, m):
        if not (1 <= m <= 12): raise ValueError('bad date')
        # flat table: index is zero-based month 0..11; leap-dependent bit only in
        # the February slot so it is read ONCE at the ONE comparison where a day
        # count depends on it, never during the per-day loop below.
        dpm = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
        if m == 2:
            extra = 1 if ((y%4 == 0) and not (y%100 == 0)) or (y%400 == 0) else 0
            return dpm[m-1] + extra
        return dpm[m-1]
    # reject a day outside its own month (leap-year February is handled above)
    if not (1 <= d1 <= days_in_month(y1, m1)):
        raise ValueError('bad date')
    if not (1 <= d2 <= days_in_month(y2, m2)):
        raise ValueError('bad date')
    # all input valid; count through the first year to that day's start then each
    # full intervening year, then the last year. Every summand is a known integer,
    # so the whole result is int -- and it may be negative (for d1 later than d2).
    t = days_through(y1) + sum(dpm[0:m1-1]) + d1 - 1
    for y in range(y1+1, y2):
        t += 365 + ((y%4 == 0 and not (y%100 == 0)) or (y%400 == 0))
    return t + sum(dpm[0:m2-1]) + d2 - days_through(y2) - 1
