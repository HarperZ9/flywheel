def format_duration(seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise ValueError("expected a non-bool int")
    sign = "-" if seconds < 0 else ""
    a = abs(seconds)
    if a < 3600:
        m, s = divmod(a, 60)
        return "%s%d:%02d" % (sign, m, s)
    h, rem = divmod(a, 3600)
    m, s = divmod(rem, 60)
    return "%s%d:%02d:%02d" % (sign, h, m, s)
