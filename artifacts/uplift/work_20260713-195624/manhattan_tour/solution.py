from typing import List

def tour_length(points: List[tuple]) -> int:
    """
    Calculate the total Manhattan distance of visiting a sequence of grid points 
    in order, as an integer.
    
    Args:
    points: A list of tuples representing coordinates [x, y] (integers).
            Each tuple should be exactly two integers and not bools or ints.
    
    Returns:
    The total Manhattan distance of visiting the points.
    """
    tour_length = 0
    for i in range(1, len(points)):
        # Calculate the distance between current point and next point
        distance = abs(points[i][0] - points[i-1][0]) + abs(points[i][1] - points[i-1][1])
        tour_length += distance
    return tour_length

# Example usage:
points = [(0, 0), (3, 4), (7, 8)]
print(tour_length(points)) # Output: 29
