def tour_length(points):
    if not isinstance(points, list):
        raise ValueError('bad point')
    if len(points) < 2:
        return 0

    total = 0

    for i in range(len(points) - 1):
        p0, p1 = points[i], points[i + 1]
        if (
            not isinstance(p0, tuple)
            or len(p0) != 2
            or not all(isinstance(x, int) and not isinstance(x, bool) for x in p0)
        ):
            raise ValueError('bad point')
        if (
            not isinstance(p1, tuple)
            or len(p1) != 2
            or not all(isinstance(x, int) and not isinstance(x, bool) for x in p1)
        ):
            raise ValueError('bad point')

        total += abs(p1[0] - p0[0]) + abs(p1[1] - p0[1])

    return total
