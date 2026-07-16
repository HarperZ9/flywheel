def tour_length(points):
    if len(points) < 2:
        return 0
    
    total_distance = 0
    for i in range(len(points) - 1):
        point1, point2 = points[i], points[i + 1]
        if not (isinstance(point1, tuple) and isinstance(point2, tuple) and len(point1) == 2 and len(point2) == 2 and all(isinstance(coord, int) for coord in point1) and all(isinstance(coord, int) for coord in point2)):
            raise ValueError('bad point')
        
        x1, y1 = point1
        x2, y2 = point2
        total_distance += abs(x2 - x1) + abs(y2 - y1)
    
    return total_distance
