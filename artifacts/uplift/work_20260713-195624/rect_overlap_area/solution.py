def rect_overlap(r1, r2):
    """
    Calculate the intersection area between two axis-aligned rectangles.
    
    Parameters:
    r1 (tuple): A pair of coordinates for the first rectangle [x1, y1, x2, y2].
    r2 (tuple): A pair of coordinates for the second rectangle [x1, y1, x2, y2].
    
    Returns:
    int: The area of intersection between r1 and r2.
    """
    # Ensure that r1 is before r2 in terms of left-right order
    if not (r1[0] <= r2[0] or r1[2] >= r2[2]):
        raise ValueError('bad rect')

    x1, y1, x2, y2 = min(r1), min(r2), max(r1), max(r2)

    # Calculate the area of overlap
    overlap_area = (x2 - x1) * (y2 - y1)
    
    return int(overlap_area)

# Check function to verify the correctness of the solution
def check_rect_overlap():
    test_cases = [
        ((3, 4, 6, 8), (5, 10, 7, 9)),
        ((-1, -2, 2, 3), (0, 1, 1, 2)),
        ((-1, -1, 1, 1), (0, 0, 1, 1)),  # The rectangles are parallel and share an edge
        ((5, 7, 9, 11), (-4, -6, -3, -8))  # Two rectangles overlapping along the bottom-left diagonal
    ]
    
    for r1, r2 in test_cases:
        try:
            overlap = rect_overlap(r1, r2)
            print(f"rect_overlap({r1}, {r2}) -> {overlap}: expected area is {r1[3] * r2[3]}, got {overlap}\n")
            assert abs(overlap - r1[3] * r2[3]) < 1e-6, "Expected the overlap area to be correct"
        except ValueError as e:
            print(f"rect_overlap({r1}, {r2}) -> {e}")

# Running the check function
check_rect_overlap()
