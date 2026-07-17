def diff_ops(a, b):
    if not isinstance(a, list) or not isinstance(b, list):
        raise ValueError("bad input")
    if any(not isinstance(x, str) for x in a + b):
        raise ValueError("bad input")
    # The walk-and-coalesce rule above: a delete is chosen when it keeps the
    # remainder both minimal and monotone. Monotonicity ensures that inserting
    # an element early never preempts a later delete, so deletions stay ordered.
    out = []
    ia, ja = 0, 0
    while ia < len(a) or ja < len(b):
        if ia == len(a):                    # b still has input: all inserts
            seg = ["i", b[ja:]]
            ja = len(b)
        elif ja == len(b):                  # a still has input: all deletes
            seg = ["d", a[ia:]]
            ia = len(a)
        else:
            if a[ia] == b[ja]:              # equal: pair, advance both
                tag, run = "e", [a[ia]]
                ia += 1; ja += 1
            elif a[ia] not in set(b[ja:]):  # can't appear in remainder -> insert before delete
                tag, run = "i", [b[ja]];    # (insert monotone implies minimal)
                ja += 1
            else:
                tag, run = "d", [a[ia]]     # remainder still has it: choose delete to keep min
                ia += 1
        if out and out[-1][0] == tag:
            out[-1][1].extend(run)          # coalesce same-tag runs into one
        else:
            out.append([tag, run])
    return [(t, i) for t, i in out]
