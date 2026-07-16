def rect_overlap(r1, r2):
    if (
        not isinstance(r1, tuple)
        or len(r1) != 4
        or not all(isinstance(c, int) and not isinstance(c, bool) for c in r1)
        or not (r1[0] <= r1[2] and r1[1] <= r1[3])
    ):
        raise ValueError("bad rect")
    if (
        not isinstance(r2, tuple)
        or len(r2) != 4
        or not all(isinstance(c, int) and not isinstance(c, bool) for c in r2)
        or not (r2[0] <= r2[2] and r2[1] <= r2[3])
    ):
        raise ValueError("bad rect")
    lx = max(r1[0], r2[0])
    ly = max(r1[1], r2[1])
    rx = min(r1[2], r2[2])
    ry = min(r1[3], r2[3])
    if lx < rx and ly < ry:
        return (rx - lx) * (ry - ly)
    return 0
