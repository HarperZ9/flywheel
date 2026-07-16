def rect_overlap(r1, r2):
    # Check if rectangles are valid
    for rect in (r1, r2):
        x1, y1, x2, y2 = rect
        if not isinstance(rect, tuple) or len(rect) != 4:
            raise ValueError('bad rect')
        if not all(isinstance(x, int) and not isinstance(x, bool) for x in rect):
            raise ValueError('bad rect')
        if not (x1 <= x2 and y1 <= y2):
            raise ValueError('bad rect')

    # Calculate the overlap
    dx = min(r1[2], r2[2]) - max(r1[0], r2[0])
    dy = min(r1[3], r2[3]) - max(r1[1], r2[1])

    if dx > 0 and dy > 0:
        return dx * dy
    else:
        return 0
