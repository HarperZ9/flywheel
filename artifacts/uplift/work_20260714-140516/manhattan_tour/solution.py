def tour_length(points):
    if len(points) < 2:
        return 0
    total = 0
    prev = points[0]
    if not isinstance(prev, tuple) or len(prev) != 2 \
            or not all(isinstance(c, int) and not isinstance(c, bool)
                       for c in prev):
        raise ValueError('bad point')
    for cur in points[1:]:
        if not isinstance(cur, tuple) or len(cur) != 2 \
                or not all(isinstance(c, int) and not isinstance(c, bool)
                           for c in cur):
            raise ValueError('bad point')
        total += abs(prev[0] - cur[0]) + abs(prev[1] - cur[1])
        prev = cur
    return total
