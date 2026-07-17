def tour_length(points):
    if len(points) < 2:
        return 0

    total_distance = 0
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        
        if not (isinstance(x1, int) and isinstance(y1, int) and isinstance(x2, int) and isinstance(y2, int)):
            raise ValueError('bad point')
        
        if any(not isinstance(coord, int) or isinstance(coord, bool) for coord in [x1, y1, x2, y2]):
            raise ValueError('bad point')

        distance = abs(x1 - x2) + abs(y1 - y2)
        total_distance += distance

    return total_distance
