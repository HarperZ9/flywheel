def rect_overlap(r1, r2):
    if not (isinstance(r1, tuple) and isinstance(r2, tuple) and len(r1) == 4 and len(r2) == 4):
        raise ValueError('rectangles must be tuples of exactly 4 integers')
    
    x1, y1, x2, y2 = r1
    a1, b1, a2, b2 = r2
    
    if not all([isinstance(i, int) for i in (x1, y1, x2, y2, a1, b1, a2, b2)]):
        raise ValueError('all coordinates must be integers')
    
    if any([x1 > x2, y1 > y2, a1 > a2, b1 > b2]):
        raise ValueError('coordinates must satisfy x1 <= x2 and y1 <= y2')
    
    # Calculate the overlap region
    dx = min(x2, a2) - max(x1, a1)
    dy = min(y2, b2) - max(y1, b1)
    
    if dx >= 0 and dy >= 0:
        return int(dx * dy)
    else:
        return 0
