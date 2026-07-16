def tour_length(points):
    def manhattan_distance(p1, p2):
        return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

    if not isinstance(points, list) or len(points) < 2:
        raise ValueError('The input should be a list with at least two points.')
    
    for point in points:
        if not (isinstance(point, tuple) and len(point) == 2
                and all(isinstance(coordinate, int) for coordinate in point)
                and not any(isinstance(coordinate, bool) for coordinate in point)):
            raise ValueError('Each element must be a tuple of exactly two integer values.')
    
    total_distance = sum(manhattan_distance(points[i], points[i + 1]) for i in range(len(points) - 1))
    return total_distance
